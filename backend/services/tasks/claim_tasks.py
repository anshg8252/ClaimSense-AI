"""Asynchronous claim processing pipeline tasks for ClaimSense AI (Phase 12).

Orchestrates sequential multi-modal pipeline execution:
Stage 1: Document OCR Extraction (Tesseract)
Stage 2: Vehicle Damage Detection (YOLOv8 CarDD)
Stage 3: NLP Accident Narrative Analysis & Chronology
Stage 4: Phase 7 Cross-Source Triangulation & Verification
Stage 5: Terminal Audit Report Snapshot Persistence (Phase 11)
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from backend.config import Config
from backend.database.db import get_db_session
from backend.database.models import Claim, ProcessingTask, ClaimImage, Document
from backend.services.ocr.document_service import ingest_extracted_claim_data, process_document
from backend.services.vision import process_claim_damage_detection
from backend.services.nlp import ClaimNLPService
from backend.services.verification import ClaimVerificationService
from backend.services.receipt import freeze_report
from backend.utils.logger import setup_logger

logger = setup_logger("claimsense.tasks")


def update_task_stage(
    task_id: str,
    status: str,
    stage: str,
    progress_percent: int,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
    result_metadata: Optional[Dict[str, Any]] = None,
    worker_id: Optional[str] = None,
) -> None:
    """Safely updates processing task stage, progress, and status in SQLite database."""
    with get_db_session() as db:
        task = db.query(ProcessingTask).filter_by(task_id=task_id).first()
        if not task:
            logger.warning(f"Task '{task_id}' not found for stage update to '{stage}'.")
            return

        task.status = status.upper()
        task.current_stage = stage.upper()
        task.progress_percent = max(0, min(100, progress_percent))
        task.updated_at = datetime.now(timezone.utc)

        if worker_id:
            task.worker_id = worker_id

        if status.upper() == "PROCESSING" and not task.started_at:
            task.started_at = datetime.now(timezone.utc)

        if status.upper() in ("COMPLETED", "FAILED", "CANCELLED"):
            task.completed_at = datetime.now(timezone.utc)

        if error_message:
            task.error_message = error_message
        if error_code:
            task.error_code = error_code

        if result_metadata:
            task.result_metadata = json.dumps(result_metadata)

        db.commit()


def execute_claim_processing_pipeline(
    claim_id: str,
    task_id: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Executes the complete end-to-end claim analysis pipeline asynchronously.

    Updates task stage transitions at each milestone:
    - INTAKE (5%)
    - OCR_PROCESSING (25%)
    - DAMAGE_ANALYSIS (55%)
    - NLP_CHRONOLOGY (75%)
    - CROSS_SOURCE_VERIFICATION (90%)
    - COMPLETED (100%)
    """
    start_time = time.time()
    logger.info(f"Starting asynchronous claim processing pipeline for claim '{claim_id}' (task_id: {task_id}).")

    if task_id:
        update_task_stage(
            task_id=task_id,
            status="PROCESSING",
            stage="INTAKE",
            progress_percent=10,
            worker_id=worker_id,
        )

    results_summary: Dict[str, Any] = {
        "claim_id": claim_id,
        "ocr_success": False,
        "vision_success": False,
        "nlp_success": False,
        "verification_success": False,
        "report_frozen": False,
    }

    try:
        # Load and validate claim existence
        with get_db_session() as db:
            claim = db.query(Claim).filter_by(claim_id=claim_id).first()
            if not claim:
                err_msg = f"Claim '{claim_id}' not found in database."
                logger.error(err_msg)
                if task_id:
                    update_task_stage(task_id, "FAILED", "INTAKE", 10, error_message=err_msg, error_code="CLAIM_NOT_FOUND")
                return {"success": False, "error": err_msg}

            claimant_name = claim.claimant_name
            policy_number = claim.policy_number
            claim_desc = claim.claim_description

            # Retrieve evidence documents as plain dicts to prevent DetachedInstanceError outside session
            doc_records = [
                {
                    "document_id": d.document_id,
                    "document_type": d.document_type,
                    "file_path": d.file_path,
                    "original_filename": d.original_filename,
                }
                for d in db.query(Document).filter_by(claim_id=claim_id).all()
            ]
            img_records = [
                {
                    "image_id": img.image_id,
                    "image_type": img.image_type,
                    "file_path": img.file_path,
                    "original_filename": img.original_filename,
                }
                for img in db.query(ClaimImage).filter_by(claim_id=claim_id).all()
            ]

        upload_root = Path(Config.UPLOAD_FOLDER)

        # -------------------------------------------------------------
        # Stage 1: Document OCR Extraction
        # -------------------------------------------------------------
        if task_id:
            update_task_stage(task_id, "PROCESSING", "OCR_PROCESSING", 25)
        logger.info(f"[{claim_id}] Stage 1: Executing Document OCR extraction...")

        processed_documents = []
        for doc in doc_records:
            if doc.get("file_path"):
                d_path = upload_root / doc["file_path"]
                if d_path.exists():
                    try:
                        orig_name = doc.get("original_filename") or d_path.name
                        proc = process_document(d_path, orig_name)
                        processed_documents.append(proc)
                    except Exception as p_err:
                        logger.warning(f"[{claim_id}] Document extraction failed for {doc.get('file_path')}: {p_err}")

        if processed_documents:
            try:
                ingest_extracted_claim_data(claim_id, processed_documents)
                results_summary["ocr_success"] = True
                logger.info(f"[{claim_id}] Document OCR extraction succeeded for {len(processed_documents)} docs.")
            except Exception as ocr_err:
                logger.warning(f"[{claim_id}] Document OCR encountered non-fatal error: {ocr_err}")
                results_summary["ocr_error"] = str(ocr_err)

        # -------------------------------------------------------------
        # Stage 2: Vehicle Damage Detection (YOLOv8)
        # -------------------------------------------------------------
        if task_id:
            update_task_stage(task_id, "PROCESSING", "DAMAGE_ANALYSIS", 55)
        logger.info(f"[{claim_id}] Stage 2: Executing YOLOv8 vehicle damage detection...")

        # Prioritize replacement vehicle photograph if present
        primary_image = next((img for img in img_records if img.get("image_type") == "REPLACEMENT_VEHICLE_ACCIDENT"), None)
        if not primary_image and img_records:
            primary_image = img_records[0]

        if primary_image:
            try:
                cv_res = process_claim_damage_detection(
                    claim_id=claim_id,
                    image_id=primary_image.get("image_id"),
                    conf_threshold=0.15,
                    force_opencv=False,
                    upload_base=upload_root,
                )
                results_summary["vision_success"] = bool(cv_res.get("success", False))
                results_summary["damages_detected"] = cv_res.get("total_detections", 0)
                logger.info(f"[{claim_id}] YOLOv8 damage detection completed: {cv_res.get('total_detections', 0)} detections.")
            except Exception as cv_err:
                logger.warning(f"[{claim_id}] YOLOv8 vision encountered non-fatal error: {cv_err}")
                results_summary["vision_error"] = str(cv_err)

        # -------------------------------------------------------------
        # Stage 3: NLP Accident Narrative Analysis
        # -------------------------------------------------------------
        if task_id:
            update_task_stage(task_id, "PROCESSING", "NLP_CHRONOLOGY", 75)
        logger.info(f"[{claim_id}] Stage 3: Executing NLP accident narrative analysis...")

        if claim_desc:
            try:
                nlp_res = ClaimNLPService.analyze_claim_narrative(
                    text=claim_desc,
                    claim_id=claim_id,
                    claimant_name=claimant_name,
                )
                results_summary["nlp_success"] = bool(nlp_res.get("success", False)) if isinstance(nlp_res, dict) else True
                logger.info(f"[{claim_id}] NLP narrative analysis completed successfully.")
            except Exception as nlp_err:
                logger.warning(f"[{claim_id}] NLP narrative analysis encountered error: {nlp_err}")
                results_summary["nlp_error"] = str(nlp_err)

        # -------------------------------------------------------------
        # Stage 4: Phase 7 Cross-Source Verification Engine
        # -------------------------------------------------------------
        if task_id:
            update_task_stage(task_id, "PROCESSING", "CROSS_SOURCE_VERIFICATION", 90)
        logger.info(f"[{claim_id}] Stage 4: Executing Phase 7 Cross-Source Triangulation...")

        try:
            verif_res = ClaimVerificationService.verify_claim(claim_id=claim_id)
            results_summary["verification_success"] = True
            if isinstance(verif_res, dict):
                results_summary["overall_status"] = verif_res.get("overall_status")
                results_summary["consistency_score"] = verif_res.get("consistency_score")
            logger.info(f"[{claim_id}] Cross-source verification completed.")
        except Exception as verif_err:
            logger.warning(f"[{claim_id}] Cross-source verification encountered error: {verif_err}")
            results_summary["verification_error"] = str(verif_err)

        # -------------------------------------------------------------
        # Stage 5: Optional Report Snapshot Persistence (Phase 11 Hybrid)
        # -------------------------------------------------------------
        try:
            frozen = freeze_report(
                claim_id=claim_id,
                user_id=None,
                report_type="VERIFICATION_AUDIT",
                upload_root=Config.UPLOAD_FOLDER,
                reports_root=Config.REPORTS_FOLDER,
            )
            if frozen:
                results_summary["report_frozen"] = True
                results_summary["report_hash"] = frozen.get("file_hash")
        except Exception as rep_err:
            logger.debug(f"[{claim_id}] Report auto-freeze skipped: {rep_err}")

        # -------------------------------------------------------------
        # Terminal Completion
        # -------------------------------------------------------------
        elapsed = round((time.time() - start_time) * 1000, 2)
        results_summary["duration_ms"] = elapsed

        # Update claim status in DB to IN_REVIEW if PENDING_ANALYSIS
        with get_db_session() as db:
            c_rec = db.query(Claim).filter_by(claim_id=claim_id).first()
            if c_rec and c_rec.status == "PENDING_ANALYSIS":
                c_rec.status = "IN_REVIEW"
                db.commit()

        if task_id:
            update_task_stage(
                task_id=task_id,
                status="COMPLETED",
                stage="COMPLETED",
                progress_percent=100,
                result_metadata=results_summary,
            )

        logger.info(f"Successfully finished asynchronous pipeline for claim '{claim_id}' in {elapsed}ms.")
        return {"success": True, "summary": results_summary}

    except Exception as exc:
        elapsed = round((time.time() - start_time) * 1000, 2)
        err_str = f"Pipeline execution failed: {str(exc)}"
        logger.error(f"[{claim_id}] {err_str}", exc_info=True)

        if task_id:
            update_task_stage(
                task_id=task_id,
                status="FAILED",
                stage="FAILED",
                progress_percent=0,
                error_message=err_str,
                error_code="PIPELINE_ERROR",
            )
        return {"success": False, "error": err_str, "duration_ms": elapsed}

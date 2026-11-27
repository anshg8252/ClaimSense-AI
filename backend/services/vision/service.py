"""Automated Phase 5 Vehicle Damage Detection Service.

Provides automatic, idempotent execution of fine-tuned YOLOv8 damage detection
across claim submission, evidence replacement, and verification pipelines.
"""

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from backend.config import Config
from backend.database.db import get_db_session
from backend.database.models import (
    Claim,
    ClaimImage,
    VehicleDamageAnalysis,
    VehicleDamageDetection,
)
from backend.services.receipt import validate_vehicle_image
from backend.services.vision.damage_detector import VehicleDamageDetector
from backend.services.vision.visualization import create_annotated_image
from backend.utils.logger import setup_logger

logger = setup_logger("claimsense.vision.service")

# Thread-safe execution locks per claim ID to guarantee idempotent execution
_claim_locks: Dict[str, threading.Lock] = {}
_global_lock = threading.Lock()


def _get_claim_lock(claim_id: str) -> threading.Lock:
    """Returns a re-entrant lock specific to a claim ID."""
    with _global_lock:
        if claim_id not in _claim_locks:
            _claim_locks[claim_id] = threading.Lock()
        return _claim_locks[claim_id]


def compute_file_sha256(file_path: Path) -> str:
    """Calculates SHA-256 digest of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def process_claim_damage_detection(
    claim_id: str,
    image_id: Optional[int] = None,
    conf_threshold: Union[float, int, Dict[Union[int, str], float]] = 0.15,
    force_opencv: bool = False,
    force_recompute: bool = False,
    upload_base: Optional[Path] = None,
) -> Dict[str, Any]:
    """Executes automated Phase 5 vehicle damage detection for a claim.

    Features:
    - Automatically discovers the latest valid photographic evidence.
    - Performs forensic verification to reject synthetic graphics / policy renders.
    - Idempotent: checks SHA-256 and DB records to prevent redundant inference.
    - Concurrency-safe: per-claim mutex ensures no duplicate parallel inference.
    - Persists VehicleDamageAnalysis and VehicleDamageDetection records to SQLite.
    - Generates and saves annotated photographs.
    - Updates claim metadata.json for backward compatibility.
    """
    if not claim_id:
        return {"success": False, "status": "invalid_request", "message": "Claim ID is required."}

    if upload_base is None:
        upload_base = Path(Config.UPLOAD_FOLDER)

    claim_dir = upload_base / claim_id
    images_dir = claim_dir / "images"

    lock = _get_claim_lock(claim_id)
    with lock:
        # 1. Resolve target vehicle photograph and ClaimImage record
        target_img_path = None
        claim_image_rec_id = None
        claim_image_orig_name = None

        with get_db_session() as db:
            claim = db.query(Claim).filter_by(claim_id=claim_id).first()
            if not claim:
                return {
                    "success": False,
                    "status": "not_found",
                    "message": f"Claim '{claim_id}' not found in database.",
                }

            if image_id is not None:
                img_rec = db.query(ClaimImage).filter_by(claim_id=claim_id, image_id=image_id).first()
            else:
                # Prioritize replacement vehicle photograph if present
                img_rec = (
                    db.query(ClaimImage)
                    .filter_by(claim_id=claim_id, image_type="REPLACEMENT_VEHICLE_ACCIDENT")
                    .order_by(ClaimImage.image_id.desc())
                    .first()
                )
                if not img_rec:
                    img_rec = (
                        db.query(ClaimImage)
                        .filter_by(claim_id=claim_id)
                        .order_by(ClaimImage.image_id.desc())
                        .first()
                    )

            if img_rec and img_rec.file_path:
                candidate = upload_base / img_rec.file_path
                if candidate.exists():
                    target_img_path = candidate
                    claim_image_rec_id = img_rec.image_id
                    claim_image_orig_name = img_rec.original_filename

        # Fallback to inspecting images directory if DB record file path is missing
        if not target_img_path and images_dir.exists():
            replacements = sorted(list(images_dir.glob("replacement_vehicle_image_*")))
            if replacements:
                target_img_path = replacements[-1]
            else:
                vehicle_imgs = sorted(list(images_dir.glob("vehicle_image_*")))
                if vehicle_imgs:
                    target_img_path = vehicle_imgs[-1]

        if not target_img_path or not target_img_path.exists():
            logger.info(f"Phase 5 auto-detection: No vehicle photograph exists on disk for claim {claim_id}.")
            return {
                "success": False,
                "status": "no_evidence",
                "message": f"No vehicle accident photograph found for claim '{claim_id}'.",
            }

        # 2. Forensic authenticity verification: prevent running inference on synthetic graphics/document cards
        img_validation = validate_vehicle_image(target_img_path)
        if not img_validation.get("is_valid_vehicle_photo"):
            logger.warning(
                f"Phase 5 auto-detection skipped for claim {claim_id}: "
                f"Uploaded file '{target_img_path.name}' flagged as {img_validation.get('status')} ({img_validation.get('reason')})"
            )
            return {
                "success": False,
                "status": "invalid_evidence",
                "message": (
                    f"Uploaded file '{target_img_path.name}' is flagged as {img_validation.get('status', 'invalid')} "
                    f"({img_validation.get('reason')}). Damage inspection cannot be performed on synthetic graphics or document renders."
                ),
                "validation": img_validation,
                "requires_replacement": True,
            }

        # 3. Calculate SHA-256 hash of the evidence photograph for idempotency
        content_hash = compute_file_sha256(target_img_path)

        # 4. Idempotency Check: Do not repeat inference unnecessarily for unchanged image
        if not force_recompute:
            with get_db_session() as db:
                query = db.query(VehicleDamageAnalysis).filter(VehicleDamageAnalysis.claim_id == claim_id)
                if claim_image_rec_id:
                    existing = query.filter(
                        (VehicleDamageAnalysis.image_id == claim_image_rec_id)
                        | (VehicleDamageAnalysis.image_hash == content_hash)
                    ).order_by(VehicleDamageAnalysis.id.desc()).first()
                else:
                    existing = query.filter(VehicleDamageAnalysis.image_hash == content_hash).order_by(VehicleDamageAnalysis.id.desc()).first()

                if existing:
                    if existing.analysis_status == "completed":
                        # Verify annotated file still exists
                        ann_path = None
                        if existing.annotated_image_path:
                            cand = upload_base / existing.annotated_image_path
                            if cand.exists():
                                ann_path = cand

                        logger.info(
                            f"Idempotent Phase 5 check: Analysis ID {existing.id} already completed for claim {claim_id} "
                            f"(image_id: {existing.image_id}, detections: {existing.total_detections}). Reusing persisted record."
                        )
                        ret = {
                            "success": True,
                            "status": "completed",
                            "already_completed": True,
                            "claim_id": claim_id,
                            "analysis": existing.to_dict(),
                        }
                        ret.update(existing.to_dict())
                        return ret
                    elif existing.analysis_status in ("processing", "running"):
                        logger.info(f"Phase 5 inference currently in progress for claim {claim_id} (Analysis ID {existing.id}).")
                        ret = {
                            "success": True,
                            "status": "processing",
                            "claim_id": claim_id,
                            "analysis": existing.to_dict(),
                        }
                        ret.update(existing.to_dict())
                        return ret

        # 5. Create processing record in database to communicate in-flight status
        rel_img_path = str(target_img_path.relative_to(upload_base))
        now_start = datetime.now(timezone.utc)
        record_id = None

        with get_db_session() as db:
            active_rec = VehicleDamageAnalysis(
                claim_id=claim_id,
                image_id=claim_image_rec_id,
                image_hash=content_hash,
                image_path=rel_img_path,
                original_image_path=rel_img_path,
                model_name="YOLOv8n-CarDD",
                model_version="1.0.0",
                detection_method="opencv_traditional_cv" if force_opencv else "yolov8_cardd",
                analysis_status="processing",
                total_detections=0,
                total_damages_detected=0,
                damage_categories="[]",
                detected_categories="[]",
                highest_confidence=0.0,
                max_confidence=0.0,
                average_confidence=0.0,
                processing_time_ms=0.0,
                inference_time_ms=0.0,
                device="cpu",
                created_at=now_start,
                updated_at=now_start,
            )
            db.add(active_rec)
            db.commit()
            record_id = active_rec.id

        # 6. Execute genuine damage detection
        logger.info(
            f"Executing Phase 5 damage detection for claim {claim_id} on image {target_img_path.name} "
            f"(conf: {conf_threshold}, force_opencv: {force_opencv})"
        )
        t0 = time.perf_counter()
        try:
            detector = VehicleDamageDetector.get_instance()
            analysis_result = detector.detect_damage(
                target_img_path,
                conf_threshold=conf_threshold,
                force_opencv_fallback=force_opencv,
            )
            t1 = time.perf_counter()
            measured_latency_ms = round((t1 - t0) * 1000.0, 2)
        except Exception as exc:
            logger.error(f"Damage detection inference failed for claim {claim_id}: {exc}", exc_info=True)
            with get_db_session() as db:
                rec = db.query(VehicleDamageAnalysis).filter_by(id=record_id).first()
                if rec:
                    rec.analysis_status = "failed"
                    rec.opencv_observations = json.dumps({"error": str(exc)})
                    rec.updated_at = datetime.now(timezone.utc)
                    db.commit()
            return {
                "success": False,
                "status": "failed",
                "analysis_status": "failed",
                "error": "Inference Error",
                "message": f"Computer vision analysis failed: {str(exc)}",
            }

        # 7. Generate annotated visualization photograph
        is_fallback = analysis_result.get("detection_method") == "opencv_traditional_cv"
        annotated_filename = f"opencv_analysis_{target_img_path.name}" if is_fallback else f"annotated_{target_img_path.name}"
        annotated_target_path = images_dir / annotated_filename
        rel_annotated_path = None
        try:
            create_annotated_image(
                target_img_path,
                analysis_result["detections"],
                output_path=annotated_target_path,
                opencv_observations=analysis_result.get("opencv_observations"),
            )
            rel_annotated_path = str(annotated_target_path.relative_to(upload_base))
        except Exception as exc:
            logger.warning(f"Could not save annotated image for claim {claim_id}: {exc}")

        # 8. Persist completed analysis and individual detection records
        avg_conf = 0.0
        if analysis_result["detections"]:
            avg_conf = sum(d["confidence"] for d in analysis_result["detections"]) / len(analysis_result["detections"])

        now_done = datetime.now(timezone.utc)
        obs_json = json.dumps(analysis_result.get("opencv_observations")) if analysis_result.get("opencv_observations") else None

        saved_analysis_dict = None
        with get_db_session() as db:
            rec = db.query(VehicleDamageAnalysis).filter_by(id=record_id).first()
            if not rec:
                rec = VehicleDamageAnalysis(id=record_id, claim_id=claim_id)
                db.add(rec)

            rec.image_id = claim_image_rec_id
            rec.image_hash = content_hash
            rec.image_path = rel_img_path
            rec.original_image_path = rel_img_path
            rec.annotated_image_path = rel_annotated_path
            rec.model_name = analysis_result["model_name"]
            rec.model_version = analysis_result["model_version"]
            rec.detection_method = analysis_result.get("detection_method", "yolov8_cardd")
            rec.model_available = analysis_result.get("model_available", True)
            rec.opencv_observations = obs_json
            rec.total_detections = int(analysis_result.get("total_detections") or 0)
            rec.total_damages_detected = int(analysis_result.get("total_detections") or 0)
            rec.damage_categories = json.dumps(analysis_result.get("damage_categories") or [])
            rec.detected_categories = json.dumps(analysis_result.get("damage_categories") or [])
            h_conf = float(analysis_result.get("highest_confidence") if analysis_result.get("highest_confidence") is not None else 0.0)
            rec.highest_confidence = h_conf
            rec.max_confidence = h_conf
            rec.average_confidence = round(float(avg_conf), 4) if avg_conf is not None else 0.0
            rec.analysis_status = "completed"
            p_time = float(analysis_result.get("processing_time_ms") or measured_latency_ms or 0.0)
            rec.processing_time_ms = p_time
            rec.inference_time_ms = p_time
            rec.device = analysis_result["device"]
            rec.updated_at = now_done

            # Persist individual detection bounding boxes
            for det in analysis_result["detections"]:
                bbox = det.get("bbox", [0, 0, 0, 0])
                det_rec = VehicleDamageDetection(
                    analysis_id=rec.id,
                    detection_index=det.get("detection_index", 1),
                    category=det.get("category", "damage"),
                    confidence=det.get("confidence", 0.0),
                    bbox_x1=bbox[0],
                    bbox_y1=bbox[1],
                    bbox_x2=bbox[2],
                    bbox_y2=bbox[3],
                    location_region=det.get("location_region", "center"),
                    created_at=now_done,
                )
                db.add(det_rec)

            db.commit()
            saved_analysis_dict = rec.to_dict()

        # 9. Update metadata.json for backward compatibility
        meta_file = claim_dir / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["latest_damage_analysis"] = saved_analysis_dict
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception as exc:
                logger.warning(f"Failed to update metadata.json for claim {claim_id}: {exc}")

        logger.info(
            f"Successfully executed Phase 5 damage detection for {claim_id}: "
            f"{analysis_result['total_detections']} detections ({', '.join(analysis_result['damage_categories']) or 'None'}) "
            f"in {measured_latency_ms}ms"
        )

        res = {
            "success": True,
            "status": "completed",
            "claim_id": claim_id,
            "analysis": saved_analysis_dict,
        }
        if saved_analysis_dict:
            res.update(saved_analysis_dict)
        return res


def trigger_claim_damage_detection_async(
    claim_id: str,
    image_id: Optional[int] = None,
    conf_threshold: Union[float, int, Dict[Union[int, str], float]] = 0.15,
    force_opencv: bool = False,
    upload_base: Optional[Path] = None,
) -> threading.Thread:
    """Spawns an asynchronous background worker to process damage detection."""
    thread = threading.Thread(
        target=process_claim_damage_detection,
        args=(claim_id, image_id, conf_threshold, force_opencv, False, upload_base),
        daemon=True,
    )
    thread.start()
    return thread

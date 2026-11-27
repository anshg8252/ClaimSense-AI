"""Claim submission, retrieval, search, and receipt routes for ClaimSense AI (Phase 3 Hardened)."""
import io
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request, session, send_file
from werkzeug.utils import secure_filename
from sqlalchemy import desc

from backend.database.db import get_db_session
from backend.database.models import (
    User,
    Claim,
    Document,
    ClaimImage,
    ExtractedInformation,
    VehicleDamageAnalysis,
    VehicleDamageDetection,
    ClaimNLPAnalysis,
    ClaimVerificationRun,
    VerificationFinding,
)
from backend.services.ocr.document_service import ingest_extracted_claim_data, process_document
from backend.services.receipt import (
    generate_claim_receipt_pdf,
    generate_document_intelligence_report_pdf,
    validate_vehicle_image,
    freeze_report,
    get_active_frozen_report,
)
from backend.services.queue.manager import queue_manager
from backend.services.vision import (
    VehicleDamageDetector,
    create_annotated_image,
    get_model_evaluation_metrics,
    process_claim_damage_detection,
)
from backend.services.nlp import ClaimNLPService
from backend.services.verification import (
    ClaimVerificationService,
    VerificationPipelineError,
)
from backend.extensions import csrf
from backend.utils.auth import get_current_user_id, can_user_access_claim
from backend.utils.logger import setup_logger
from backend.utils.validators import (
    generate_claim_id,
    is_valid_claim_id_format,
    validate_claim_form_fields,
    validate_claim_files,
    sanitize_and_resolve_path,
)

logger = setup_logger("claimsense.claims")

claims_bp = Blueprint("claims", __name__)


@claims_bp.route("/claims", methods=["POST"])
def submit_claim():
    """Handles authenticated multipart claim submission.

    Validates required text fields, file extensions, and file signatures,
    safely writes uploads to isolated disk directories, and persists
    structured claim and evidence records in SQLite database linked
    strictly to the authenticated session user.
    """
    # 1. Enforce active user session authentication
    current_user_id = session.get("user_id")
    if not current_user_id:
        return jsonify({
            "success": False,
            "error": "Unauthorized",
            "message": "Authentication required. Please sign in before submitting an insurance claim.",
        }), 401

    with get_db_session() as db:
        user = db.query(User).filter_by(id=current_user_id).first()
        if not user or not user.is_active:
            session.clear()
            return jsonify({
                "success": False,
                "error": "Unauthorized",
                "message": "An active user account is required to submit a claim.",
            }), 401

    form_data = request.form.to_dict()
    files_dict = request.files

    # 2. Validate text fields
    fields_valid, field_errors = validate_claim_form_fields(form_data)
    if not fields_valid:
        logger.warning(f"Claim submission rejected due to form errors: {field_errors}")
        return jsonify({
            "success": False,
            "error": "Validation Error",
            "message": "Form validation failed.",
            "details": field_errors,
        }), 400

    # 3. Validate uploaded files (presence, extensions, 0-byte checks, signatures)
    files_valid, file_errors = validate_claim_files(files_dict)
    if not files_valid:
        logger.warning(f"Claim submission rejected due to file errors: {file_errors}")
        return jsonify({
            "success": False,
            "error": "Validation Error",
            "message": "Uploaded files validation failed.",
            "details": file_errors,
        }), 400

    claim_dir = None
    try:
        # 4. Generate unique claim ID and isolated directories
        claim_id = generate_claim_id()
        upload_base = Path(current_app.config["UPLOAD_FOLDER"])
        claim_dir = upload_base / claim_id
        docs_dir = claim_dir / "documents"
        images_dir = claim_dir / "images"

        docs_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        saved_files = {}

        # 5. Save evidentiary documents safely
        doc_fields = ["policy_document", "claim_form", "invoice_document"]
        doc_type_mapping = {
            "policy_document": "POLICY_DOCUMENT",
            "claim_form": "CLAIM_FORM",
            "invoice_document": "INVOICE",
        }

        saved_docs_metadata = []
        for field in doc_fields:
            file_obj = files_dict[field]
            clean_filename = secure_filename(file_obj.filename)
            prefix = field
            dest_filename = f"{prefix}_{clean_filename}" if clean_filename else f"{prefix}.bin"
            target_path = sanitize_and_resolve_path(docs_dir, dest_filename)
            file_obj.save(str(target_path))

            ext = clean_filename.rsplit(".", 1)[-1].lower() if "." in clean_filename else ""
            size_bytes = target_path.stat().st_size
            rel_path = str(target_path.relative_to(upload_base))

            saved_files[field] = {
                "original_name": file_obj.filename,
                "saved_as": dest_filename,
                "relative_path": rel_path,
                "size_bytes": size_bytes,
            }
            saved_docs_metadata.append({
                "document_type": doc_type_mapping.get(field, "OTHER"),
                "file_path": rel_path,
                "original_filename": file_obj.filename,
                "stored_filename": dest_filename,
                "file_extension": ext,
                "file_size": size_bytes,
            })

        # 6. Save vehicle image safely
        img_file = files_dict["vehicle_image"]
        clean_img_name = secure_filename(img_file.filename)
        dest_img_name = f"vehicle_image_{clean_img_name}" if clean_img_name else "vehicle_image.jpg"
        target_img_path = sanitize_and_resolve_path(images_dir, dest_img_name)
        img_file.save(str(target_img_path))

        img_ext = clean_img_name.rsplit(".", 1)[-1].lower() if "." in clean_img_name else ""
        img_size_bytes = target_img_path.stat().st_size
        img_rel_path = str(target_img_path.relative_to(upload_base))

        saved_files["vehicle_image"] = {
            "original_name": img_file.filename,
            "saved_as": dest_img_name,
            "relative_path": img_rel_path,
            "size_bytes": img_size_bytes,
        }

        # 7. Persist claim metadata JSON (Backward compatibility)
        submission_time = datetime.now(timezone.utc)
        incident_location = form_data.get("incident_location", "").strip() or None
        metadata = {
            "claim_id": claim_id,
            "user_id": current_user_id,
            "claimant_name": form_data["claimant_name"].strip(),
            "policy_number": form_data["policy_number"].strip(),
            "vehicle_number": form_data["vehicle_number"].strip(),
            "accident_date": form_data["accident_date"].strip(),
            "incident_location": incident_location,
            "claim_description": form_data["claim_description"].strip(),
            "files": saved_files,
            "status": "SUBMITTED",
            "created_at": submission_time.isoformat(),
        }

        metadata_path = claim_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # 8. Persist to SQLite Database linked to authenticated user
        with get_db_session() as db:
            claim_record = Claim(
                claim_id=claim_id,
                user_id=current_user_id,
                claimant_name=metadata["claimant_name"],
                policy_number=metadata["policy_number"],
                vehicle_number=metadata["vehicle_number"],
                accident_date=metadata["accident_date"],
                incident_location=incident_location,
                claim_description=metadata["claim_description"],
                status="SUBMITTED",
                created_at=submission_time,
                updated_at=submission_time,
            )
            db.add(claim_record)
            db.flush()

            for doc_meta in saved_docs_metadata:
                doc_record = Document(
                    claim_id=claim_id,
                    document_type=doc_meta["document_type"],
                    file_path=doc_meta["file_path"],
                    original_filename=doc_meta["original_filename"],
                    stored_filename=doc_meta["stored_filename"],
                    file_extension=doc_meta["file_extension"],
                    file_size=doc_meta["file_size"],
                    created_at=submission_time,
                )
                db.add(doc_record)

            img_record = ClaimImage(
                claim_id=claim_id,
                image_type="VEHICLE_ACCIDENT",
                file_path=img_rel_path,
                original_filename=img_file.filename,
                stored_filename=dest_img_name,
                file_extension=img_ext,
                file_size=img_size_bytes,
                created_at=submission_time,
            )
            db.add(img_record)
            db.flush()
            image_record_id = img_record.image_id

        # Phase 12: Dual-Mode Asynchronous Intake vs Synchronous Fallback
        async_requested = request.args.get("async", "").lower() in ("true", "1")
        sync_requested = request.args.get("sync", "").lower() in ("true", "1")
        async_config = current_app.config.get("ASYNC_PROCESSING_ENABLED", False)

        is_async = (async_requested or async_config) and not sync_requested

        if is_async:
            task, is_new = queue_manager.enqueue_claim_task(
                claim_id=claim_id,
                user_id=current_user_id,
                sync=False,
            )
            logger.info(f"Claim {claim_id} accepted for async processing (task_id: {task.task_id})")

            return jsonify({
                "success": True,
                "claim_id": claim_id,
                "task_id": task.task_id,
                "status": task.status.lower() if hasattr(task, "status") else "queued",
                "status_url": f"/api/claims/{claim_id}/status",
                "receipt_url": f"/api/claims/{claim_id}/receipt",
                "message": "Claim accepted for asynchronous processing",
                "data": {
                    "claim_id": claim_id,
                    "user_id": current_user_id,
                    "claimant_name": metadata["claimant_name"],
                    "policy_number": metadata["policy_number"],
                    "vehicle_number": metadata["vehicle_number"],
                    "accident_date": metadata["accident_date"],
                    "claim_description": metadata["claim_description"],
                    "status": "QUEUED",
                    "files_count": len(saved_files),
                    "created_at": metadata["created_at"],
                },
            }), 202

        # 8. Phase 4 document intelligence pipeline (best-effort extraction - synchronous fallback)
        processed_documents = []
        for field in doc_fields:
            file_obj = files_dict[field]
            stored_path = upload_base / saved_files[field]["relative_path"]
            processed = process_document(stored_path, file_obj.filename)
            processed_documents.append(processed)

        try:
            ingest_extracted_claim_data(claim_id, processed_documents)
        except Exception as exc:
            logger.warning(f"Best-effort Phase 4 extraction storage skipped for claim {claim_id}: {exc}")

        # 9. Phase 5 automated vehicle damage detection pipeline
        auto_damage_analysis = None
        try:
            auto_damage_analysis = process_claim_damage_detection(
                claim_id=claim_id,
                image_id=image_record_id,
                upload_base=upload_base,
            )
            if auto_damage_analysis and auto_damage_analysis.get("analysis_status") == "completed":
                logger.info(
                    f"Automated Phase 5 damage detection succeeded for new claim {claim_id}: "
                    f"{auto_damage_analysis.get('total_detections', 0)} detections"
                )
            elif auto_damage_analysis and auto_damage_analysis.get("requires_replacement"):
                logger.info(f"Phase 5 skipped for new claim {claim_id}: Non-photographic/synthetic graphic uploaded")
        except Exception as exc:
            logger.warning(f"Automated Phase 5 damage detection failed/skipped for claim {claim_id}: {exc}")

        # Phase 8 Shadow Trial: Non-blocking background dispatch (Strictly isolated, disabled by default)
        try:
            from backend.services.vision.shadow_worker import get_shadow_manager
            shadow_mgr = get_shadow_manager()
            if shadow_mgr.is_enabled():
                cand_img_path = upload_base / img_rel_path if img_rel_path else None
                if cand_img_path and cand_img_path.exists():
                    shadow_mgr.enqueue_shadow_job(
                        claim_id=claim_id,
                        image_path=cand_img_path,
                        prod_detections=auto_damage_analysis or {},
                    )
        except Exception as shadow_hook_exc:
            logger.warning(f"Shadow trial dispatch safely bypassed for claim {claim_id}: {shadow_hook_exc}")

        logger.info(f"Successfully processed and stored claim in disk and SQLite: {claim_id}")

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "message": "Claim submitted successfully",
            "receipt_url": f"/api/claims/{claim_id}/receipt",
            "damage_analysis": auto_damage_analysis,
            "data": {
                "claim_id": claim_id,
                "user_id": current_user_id,
                "claimant_name": metadata["claimant_name"],
                "policy_number": metadata["policy_number"],
                "vehicle_number": metadata["vehicle_number"],
                "accident_date": metadata["accident_date"],
                "claim_description": metadata["claim_description"],
                "status": "SUBMITTED",
                "files_count": len(saved_files),
                "created_at": metadata["created_at"],
            },
        }), 201

    except Exception as e:
        logger.error(f"Error while processing claim submission: {str(e)}", exc_info=True)
        # Clean up partially written directory on failure
        if claim_dir and claim_dir.exists():
            try:
                shutil.rmtree(claim_dir, ignore_errors=True)
            except Exception:
                pass
        return jsonify({
            "success": False,
            "error": "Server Error",
            "message": "Failed to store claim submission files or database record.",
        }), 500


@claims_bp.route("/claims/<claim_id>", methods=["GET"])
def get_claim(claim_id: str):
    """Retrieves submitted claim metadata by Claim ID with strict access control."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()

        if claim:
            # Enforce access authorization
            if not can_user_access_claim(claim, user_id, user_role):
                if not user_id:
                    return jsonify({
                        "success": False,
                        "error": "Unauthorized",
                        "message": "Authentication required to access this claim record.",
                    }), 401
                return jsonify({
                    "success": False,
                    "error": "Forbidden",
                    "message": "You do not have permission to view this claim.",
                }), 403

            claim_data = claim.to_dict(include_evidence=True)
            upload_base = Path(current_app.config["UPLOAD_FOLDER"])
            metadata_path = upload_base / claim_id / "metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if "vehicle_image_validation" in meta:
                        claim_data["vehicle_image_validation"] = meta["vehicle_image_validation"]
                        if "vehicle_image" in claim_data.get("files", {}):
                            claim_data["files"]["vehicle_image"]["validation_status"] = meta["vehicle_image_validation"].get("status")
                    if "archived_images" in meta:
                        claim_data["archived_images"] = meta["archived_images"]
                except Exception:
                    pass

            return jsonify({
                "success": True,
                "data": claim_data,
            }), 200

    # Fallback to metadata.json on disk if database record is missing
    upload_base = Path(current_app.config["UPLOAD_FOLDER"])
    metadata_path = upload_base / claim_id / "metadata.json"

    if not metadata_path.exists():
        return jsonify({
            "success": False,
            "error": "Not Found",
            "message": f"Claim with ID '{claim_id}' was not found.",
        }), 404

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Enforce authorization on disk fallback read
        if not can_user_access_claim_dict(data, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to access this claim record.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to view this claim.",
            }), 403

        return jsonify({
            "success": True,
            "data": data,
        }), 200
    except Exception as e:
        logger.error(f"Failed to read metadata for claim {claim_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Server Error",
            "message": "Failed to read claim records.",
        }), 500


@claims_bp.route("/claims/<claim_id>/extracted", methods=["GET"])
def get_claim_extractions(claim_id: str):
    """Fetch database-backed extracted fields for a claim as part of Phase 4 analysis."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to view extracted claim fields.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to access extracted claim fields.",
            }), 403

        rows = db.query(ExtractedInformation).filter_by(claim_id=claim_id).order_by(ExtractedInformation.created_at.asc()).all()
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "count": len(rows),
            "fields": [record.to_dict() for record in rows],
        }), 200


@claims_bp.route("/claims/policy/<policy_number>", methods=["GET"])
def search_claims_by_policy(policy_number: str):
    """Searches and retrieves all claims associated with a specific Policy Number."""
    clean_policy = (policy_number or "").strip()
    if not clean_policy:
        return jsonify({
            "success": False,
            "error": "Validation Error",
            "message": "Policy number parameter cannot be empty.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Unauthorized",
            "message": "Authentication required to search claims by policy number.",
        }), 401

    with get_db_session() as db:
        query = db.query(Claim).filter(Claim.policy_number.ilike(clean_policy))

        # Restrict standard users to their own claims; assessors and admins can search globally
        if user_role not in ("assessor", "admin"):
            query = query.filter_by(user_id=user_id)

        claims = query.order_by(desc(Claim.created_at)).all()

        if not claims:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"No claims found matching policy number '{clean_policy}'.",
                "count": 0,
                "claims": [],
            }), 404

        return jsonify({
            "success": True,
            "policy_number": clean_policy,
            "count": len(claims),
            "claims": [c.to_dict(include_evidence=True) for c in claims],
        }), 200


@claims_bp.route("/claims/search", methods=["GET"])
def search_claims():
    """Unified search endpoint for claims by Claim ID or Policy Number."""
    user_id = session.get("user_id")
    user_role = session.get("role")

    if not user_id and user_role not in ("assessor", "admin"):
        return jsonify({
            "success": False,
            "error": "Unauthorized",
            "message": "Authentication required to search claims.",
        }), 401

    query_str = request.args.get("q", "").strip()
    if not query_str:
        return jsonify({
            "success": False,
            "error": "Validation Error",
            "message": "Search query must not be empty.",
        }), 400

    with get_db_session() as db:
        query = db.query(Claim)
        if user_role not in ("assessor", "admin"):
            query = query.filter_by(user_id=user_id)

        query = query.filter(
            (Claim.claim_id.ilike(f"%{query_str}%")) | (Claim.policy_number.ilike(f"%{query_str}%"))
        )
        claims = query.order_by(desc(Claim.created_at)).all()

        return jsonify({
            "success": True,
            "query": query_str,
            "count": len(claims),
            "claims": [c.to_dict(include_evidence=True) for c in claims],
        }), 200


@claims_bp.route("/my-claims", methods=["GET"])
def get_my_claims():
    """Retrieves all claims submitted by the currently authenticated user."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({
            "success": False,
            "error": "Unauthorized",
            "message": "Authentication required to access personal claim history.",
        }), 401

    with get_db_session() as db:
        claims = (
            db.query(Claim)
            .filter_by(user_id=user_id)
            .order_by(desc(Claim.created_at))
            .all()
        )
        return jsonify({
            "success": True,
            "count": len(claims),
            "claims": [c.to_dict(include_evidence=True) for c in claims],
        }), 200


@claims_bp.route("/claims/<claim_id>/document-report", methods=["GET"])
@claims_bp.route("/claims/<claim_id>/report", methods=["GET"])
def get_claim_document_report(claim_id: str):
    """Serves the Phase 4/10/11 document intelligence report PDF for an eligible claim.

    If an immutable frozen snapshot exists (Phase 11 Hybrid Two-Tier model), serves the
    persisted static file. Otherwise, generates the report dynamically in-memory.
    """
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to access this document intelligence report.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You are not authorized to access this document intelligence report.",
            }), 403

        # Check for active frozen report snapshot first (Phase 11 Hybrid Two-Tier model)
        frozen = get_active_frozen_report(claim_id, report_type="VERIFICATION_AUDIT")
        if frozen and Path(frozen["report_path"]).exists():
            resp = send_file(
                frozen["report_path"],
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"document_report_{claim_id}.pdf",
            )
            if frozen.get("file_hash"):
                resp.headers["ETag"] = f'"{frozen["file_hash"]}"'
            resp.headers["X-Report-Source"] = "persisted-snapshot"
            return resp

        claim_dict = claim.to_dict(include_evidence=True)
        extracted_rows = [
            row.to_dict() for row in db.query(ExtractedInformation)
            .filter_by(claim_id=claim_id)
            .order_by(ExtractedInformation.created_at.asc())
            .all()
        ]

    try:
        pdf_bytes = generate_document_intelligence_report_pdf(
            claim_dict,
            extracted_rows,
            upload_root=current_app.config.get("UPLOAD_FOLDER"),
        )
        resp = send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"document_report_{claim_id}.pdf",
        )
        resp.headers["X-Report-Source"] = "dynamic-stream"
        return resp
    except Exception as e:
        logger.error(f"Error generating document intelligence report for claim {claim_id}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Report Generation Error",
            "message": "Failed to generate the document intelligence report.",
        }), 500


@claims_bp.route("/claims/<claim_id>/freeze-report", methods=["POST"])
def freeze_claim_report(claim_id: str):
    """Generates and freezes an immutable audit report snapshot for a claim (Phase 11)."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to freeze audit reports.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You are not authorized to freeze audit reports for this claim.",
            }), 403

    try:
        report_meta = freeze_report(
            claim_id=claim_id,
            user_id=user_id,
            report_type="VERIFICATION_AUDIT",
            upload_root=current_app.config.get("UPLOAD_FOLDER"),
            reports_root=current_app.config.get("REPORTS_FOLDER"),
        )
        if not report_meta:
            return jsonify({
                "success": False,
                "error": "Freeze Report Failed",
                "message": "Unable to generate or persist audit report snapshot.",
            }), 500

        return jsonify({
            "success": True,
            "message": f"Immutable audit report snapshot created for claim '{claim_id}'.",
            "report": report_meta,
        }), 201
    except Exception as e:
        logger.error(f"Error freezing audit report for claim {claim_id}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Freeze Report Error",
            "message": str(e),
        }), 500


@claims_bp.route("/claims/<claim_id>/evidence/<file_type>", methods=["GET"])
def get_claim_evidence_file(claim_id: str, file_type: str):
    """Safely serves an uploaded evidence document or photograph for a claim."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to view evidence files.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You are not authorized to view evidence for this claim.",
            }), 403

        upload_base = Path(current_app.config["UPLOAD_FOLDER"])
        target_file_path = None
        target_filename = None

        doc_type_mapping = {
            "policy": "POLICY_DOCUMENT",
            "policy_document": "POLICY_DOCUMENT",
            "claim_form": "CLAIM_FORM",
            "invoice": "INVOICE",
            "invoice_document": "INVOICE",
        }

        clean_type = file_type.lower()
        if clean_type in doc_type_mapping:
            doc = db.query(Document).filter_by(
                claim_id=claim_id,
                document_type=doc_type_mapping[clean_type],
            ).first()
            if doc and doc.file_path:
                target_file_path = upload_base / doc.file_path
                target_filename = doc.original_filename
        elif clean_type in ("replacement_image", "replacement_photo"):
            img = (
                db.query(ClaimImage)
                .filter_by(claim_id=claim_id, image_type="REPLACEMENT_VEHICLE_ACCIDENT")
                .order_by(ClaimImage.image_id.desc())
                .first()
            )
            if img and img.file_path:
                target_file_path = upload_base / img.file_path
                target_filename = img.original_filename
        elif clean_type in ("original_image", "original_photo"):
            img = (
                db.query(ClaimImage)
                .filter_by(claim_id=claim_id, image_type="VEHICLE_ACCIDENT")
                .order_by(ClaimImage.image_id.asc())
                .first()
            )
            if img and img.file_path:
                target_file_path = upload_base / img.file_path
                target_filename = img.original_filename
        elif clean_type in ("image", "vehicle_image", "photo"):
            # Check replacement image first, then latest uploaded image
            img = (
                db.query(ClaimImage)
                .filter_by(claim_id=claim_id, image_type="REPLACEMENT_VEHICLE_ACCIDENT")
                .order_by(ClaimImage.image_id.desc())
                .first()
            )
            if not img:
                img = db.query(ClaimImage).filter_by(claim_id=claim_id).order_by(ClaimImage.image_id.desc()).first()
            if img and img.file_path:
                target_file_path = upload_base / img.file_path
                target_filename = img.original_filename

        if not target_file_path or not target_file_path.exists():
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Evidence file for '{file_type}' was not found.",
            }), 404

        as_attachment = request.args.get("download", "0") == "1"
        return send_file(
            str(target_file_path),
            as_attachment=as_attachment,
            download_name=target_filename,
        )


@claims_bp.route("/claims/<claim_id>/receipt", methods=["GET"])
def get_claim_receipt(claim_id: str):
    """Generates and serves official claim submission receipt in PDF or JSON format with authorization."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()

        claim_dict = None
        if claim:
            if not can_user_access_claim(claim, user_id, user_role):
                if not user_id:
                    return jsonify({
                        "success": False,
                        "error": "Unauthorized",
                        "message": "Authentication required to access this claim receipt.",
                    }), 401
                return jsonify({
                    "success": False,
                    "error": "Forbidden",
                    "message": "You are not authorized to download this claim receipt.",
                }), 403
            claim_dict = claim.to_dict(include_evidence=True)
        else:
            # Fallback to metadata.json on disk if available
            upload_base = Path(current_app.config["UPLOAD_FOLDER"])
            metadata_path = upload_base / claim_id / "metadata.json"
            if not metadata_path.exists():
                return jsonify({
                    "success": False,
                    "error": "Not Found",
                    "message": f"Claim with ID '{claim_id}' was not found.",
                }), 404

            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    claim_dict = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read disk metadata for claim receipt {claim_id}: {e}")
                return jsonify({
                    "success": False,
                    "error": "Server Error",
                    "message": "Failed to parse claim records.",
                }), 500

            # Enforce authorization on disk fallback receipt generation
            if not can_user_access_claim_dict(claim_dict, user_id, user_role):
                if not user_id:
                    return jsonify({
                        "success": False,
                        "error": "Unauthorized",
                        "message": "Authentication required to access this claim receipt.",
                    }), 401
                return jsonify({
                    "success": False,
                    "error": "Forbidden",
                    "message": "You are not authorized to download this claim receipt.",
                }), 403

    # Format check: format=pdf (default) vs format=json
    requested_format = request.args.get("format", "pdf").lower()
    if requested_format == "json" or request.headers.get("Accept") == "application/json":
        return jsonify({
            "success": True,
            "receipt_type": "SUBMISSION_RECEIPT",
            "claim_id": claim_dict.get("claim_id"),
            "policy_number": claim_dict.get("policy_number"),
            "claimant_name": claim_dict.get("claimant_name"),
            "vehicle_number": claim_dict.get("vehicle_number"),
            "accident_date": claim_dict.get("accident_date"),
            "claim_description": claim_dict.get("claim_description"),
            "status": claim_dict.get("status", "SUBMITTED"),
            "created_at": claim_dict.get("created_at"),
            "documents": claim_dict.get("documents", []),
            "images": claim_dict.get("images", []),
            "disclaimer": (
                "This receipt confirms submission and registration of the claim evidence. "
                "It does not represent approval, rejection, fraud confirmation, or final "
                "insurance claim verification."
            ),
        }), 200

    # Generate PDF
    try:
        pdf_bytes = generate_claim_receipt_pdf(claim_dict)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"receipt_{claim_id}.pdf",
        )
    except Exception as e:
        logger.error(f"Error generating PDF receipt for claim {claim_id}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Receipt Generation Error",
            "message": "Failed to generate receipt PDF.",
        }), 500


@claims_bp.route("/claims/<claim_id>/replace-image", methods=["POST"])
@claims_bp.route("/claims/<claim_id>/images", methods=["POST"])
@csrf.exempt
def replace_claim_image(claim_id: str):
    """Allows uploading a replacement actual accident photograph for a claim.

    Preserves the original uploaded file on disk and in history, executes
    forensic vehicle image validation on the new photograph, and updates the
    claim evidence validation status.
    """
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to replace claim evidence image.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You are not authorized to modify evidence for this claim.",
            }), 403

        files_dict = request.files
        img_file = files_dict.get("vehicle_image") or files_dict.get("image") or files_dict.get("file")
        if not img_file or not img_file.filename:
            return jsonify({
                "success": False,
                "error": "Validation Error",
                "message": "No vehicle photograph file was provided in the request.",
            }), 400

        clean_img_name = secure_filename(img_file.filename)
        ext = clean_img_name.rsplit(".", 1)[-1].lower() if "." in clean_img_name else ""
        if ext not in {"jpg", "jpeg", "png"}:
            return jsonify({
                "success": False,
                "error": "Validation Error",
                "message": "Invalid file format. Vehicle photograph must be a JPEG or PNG image.",
            }), 400

        upload_base = Path(current_app.config["UPLOAD_FOLDER"])
        claim_dir = upload_base / claim_id
        images_dir = claim_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        dest_img_name = f"replacement_vehicle_image_{clean_img_name}" if clean_img_name else "replacement_vehicle_image.jpg"
        target_img_path = sanitize_and_resolve_path(images_dir, dest_img_name)
        img_file.save(str(target_img_path))

        img_size_bytes = target_img_path.stat().st_size
        img_rel_path = str(target_img_path.relative_to(upload_base))

        # Forensic image validation
        validation = validate_vehicle_image(target_img_path)
        if not validation.get("is_valid_vehicle_photo"):
            logger.warning(
                f"Replacement vehicle photograph rejected for {claim_id}: {clean_img_name} "
                f"flagged as {validation.get('status')} ({validation.get('reason')})"
            )
            # Remove invalid uploaded replacement file from disk to avoid clutter
            try:
                if target_img_path.exists():
                    target_img_path.unlink()
            except Exception:
                pass
            return jsonify({
                "success": False,
                "error": "Invalid Vehicle Evidence",
                "message": (
                    f"Uploaded replacement file '{clean_img_name}' is flagged as {validation.get('status', 'invalid')} "
                    f"({validation.get('reason')}). Replacement photograph must be an authentic vehicle damage photo."
                ),
                "validation": validation,
                "requires_replacement": True,
            }), 400

        # Record replacement image in database while preserving original flagged file in audit history
        existing_img = db.query(ClaimImage).filter_by(claim_id=claim_id).order_by(ClaimImage.created_at.desc()).first()
        prev_filename = existing_img.original_filename if existing_img else "unknown"

        new_img_rec = ClaimImage(
            claim_id=claim_id,
            image_type="REPLACEMENT_VEHICLE_ACCIDENT",
            file_path=img_rel_path,
            original_filename=img_file.filename,
            stored_filename=dest_img_name,
            file_extension=ext,
            file_size=img_size_bytes,
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_img_rec)
        db.commit()
        new_image_id = new_img_rec.image_id

        # Automatically execute Phase 5 damage detection for authentic replacement photograph
        auto_damage_analysis = None
        if validation.get("is_valid_vehicle_photo"):
            try:
                auto_damage_analysis = process_claim_damage_detection(
                    claim_id=claim_id,
                    image_id=new_image_id,
                    upload_base=upload_base,
                )
                if auto_damage_analysis and auto_damage_analysis.get("analysis_status") == "completed":
                    logger.info(
                        f"Automated Phase 5 damage detection succeeded for replacement image on {claim_id}: "
                        f"{auto_damage_analysis.get('total_detections', 0)} detections"
                    )
            except Exception as exc:
                logger.warning(f"Automated Phase 5 damage detection failed for replacement photo on {claim_id}: {exc}")

        # Update metadata.json while preserving previous files in history
        metadata_path = claim_dir / "metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if "archived_images" not in meta:
                    meta["archived_images"] = []
                if "vehicle_image" in meta.get("files", {}):
                    meta["archived_images"].append(meta["files"]["vehicle_image"])
                meta["files"]["vehicle_image"] = {
                    "original_name": img_file.filename,
                    "saved_as": dest_img_name,
                    "relative_path": img_rel_path,
                    "size_bytes": img_size_bytes,
                    "replaced_at": datetime.now(timezone.utc).isoformat(),
                    "validation_status": validation.get("status"),
                }
                meta["vehicle_image_validation"] = validation
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception as exc:
                logger.warning(f"Could not update metadata.json for claim {claim_id}: {exc}")

        logger.info(f"Replacement vehicle photograph uploaded for claim {claim_id}: {clean_img_name} ({validation.get('status')})")

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "message": "Replacement accident photograph uploaded and evaluated successfully.",
            "original_preserved": True,
            "archived_image": prev_filename,
            "new_image": {
                "original_filename": img_file.filename,
                "stored_filename": dest_img_name,
                "relative_path": img_rel_path,
                "file_size": img_size_bytes,
            },
            "validation": validation,
            "damage_analysis": auto_damage_analysis,
        }), 200


@claims_bp.route("/claims/<claim_id>/analyze-damage", methods=["POST"])
@csrf.exempt
def analyze_claim_vehicle_damage(claim_id: str):
    """Executes AI vehicle damage detection using YOLOv8 fine-tuned on CarDD.

    Localizes damages, identifies categories, generates annotated image,
    and stores results in SQLite database.
    """
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to analyze damage for this claim.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to analyze damage for this claim.",
            }), 403

        # Locate vehicle photograph
        upload_base = Path(current_app.config["UPLOAD_FOLDER"])
        claim_dir = upload_base / claim_id
        images_dir = claim_dir / "images"

        target_img_path = None
        claim_image_rec = None

        # Prioritize replacement photograph first, then latest ClaimImage in DB
        rep_img = (
            db.query(ClaimImage)
            .filter_by(claim_id=claim_id, image_type="REPLACEMENT_VEHICLE_ACCIDENT")
            .order_by(desc(ClaimImage.image_id))
            .first()
        )
        if rep_img and rep_img.file_path:
            candidate = upload_base / rep_img.file_path
            if candidate.exists():
                target_img_path = candidate
                claim_image_rec = rep_img

        if not target_img_path:
            db_img = (
                db.query(ClaimImage)
                .filter_by(claim_id=claim_id)
                .order_by(desc(ClaimImage.image_id))
                .first()
            )
            if db_img and db_img.file_path:
                candidate = upload_base / db_img.file_path
                if candidate.exists():
                    target_img_path = candidate
                    claim_image_rec = db_img

        # Fallback to inspecting images directory on disk
        if not target_img_path and images_dir.exists():
            replacements = sorted(list(images_dir.glob("replacement_vehicle_image_*")))
            if replacements:
                target_img_path = replacements[-1]
            else:
                vehicle_imgs = sorted(list(images_dir.glob("vehicle_image_*")))
                if vehicle_imgs:
                    target_img_path = vehicle_imgs[-1]

        if not target_img_path or not target_img_path.exists():
            return jsonify({
                "success": False,
                "error": "Missing Evidence",
                "message": "No vehicle accident photograph found for this claim.",
            }), 400

        # Forensic authenticity verification: prevent running inference on synthetic graphics/document cards
        img_validation = validate_vehicle_image(target_img_path)
        if not img_validation.get("is_valid_vehicle_photo"):
            return jsonify({
                "success": False,
                "error": "Invalid Vehicle Evidence",
                "message": (
                    f"Uploaded file '{target_img_path.name}' is flagged as {img_validation.get('status', 'invalid')} "
                    f"({img_validation.get('reason')}). Damage inspection cannot be performed on synthetic graphics or document renders. "
                    f"Please upload an authentic replacement vehicle photograph before running AI damage analysis."
                ),
                "validation": img_validation,
                "requires_replacement": True,
            }), 400

        # Allow confidence threshold override (scalar or per-class dict) and fallback mode from JSON or query params
        req_json = request.get_json(silent=True)
        if req_json is None:
            req_json = {}
        elif not isinstance(req_json, dict):
            return jsonify({
                "success": False,
                "error": "Validation Error",
                "message": "Request JSON body must be an object.",
            }), 400

        if "conf_threshold" in req_json and req_json["conf_threshold"] is not None:
            raw_conf = req_json["conf_threshold"]
            if isinstance(raw_conf, bool):
                return jsonify({
                    "success": False,
                    "error": "Invalid Threshold",
                    "message": "conf_threshold must be a numeric scalar or per-class dictionary, got bool.",
                }), 400
            if isinstance(raw_conf, dict):
                conf_thresh = raw_conf
            elif isinstance(raw_conf, (int, float)):
                conf_thresh = float(raw_conf)
            else:
                return jsonify({
                    "success": False,
                    "error": "Invalid Threshold",
                    "message": f"conf_threshold must be a numeric scalar or per-class dictionary, got {type(raw_conf).__name__}.",
                }), 400
        elif "conf" in request.args and str(request.args.get("conf", "")).strip() != "":
            try:
                conf_thresh = float(request.args.get("conf"))
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "Invalid Threshold",
                    "message": f"Query parameter 'conf' must be a numeric value between 0.0 and 1.0.",
                }), 400
        else:
            conf_thresh = 0.15

        try:
            VehicleDamageDetector.get_instance()._resolve_conf_thresholds(conf_thresh)
        except (ValueError, TypeError) as thresh_exc:
            return jsonify({
                "success": False,
                "error": "Invalid Threshold",
                "message": str(thresh_exc),
            }), 400

        force_fallback = bool(req_json.get("force_opencv") or req_json.get("fallback") or request.args.get("fallback") == "true")
        force_recompute = bool(
            req_json.get("force")
            or req_json.get("force_recompute")
            or request.args.get("force") == "true"
            or force_fallback
        )

        # Execute unified damage detection pipeline safely
        try:
            analysis_dict = process_claim_damage_detection(
                claim_id=claim_id,
                image_id=claim_image_rec.image_id if claim_image_rec else None,
                conf_threshold=conf_thresh,
                force_opencv=force_fallback,
                force_recompute=force_recompute,
                upload_base=upload_base,
            )
        except Exception as exc:
            logger.error(f"Damage detection failed unexpectedly for {claim_id}: {exc}", exc_info=True)
            return jsonify({
                "success": False,
                "error": "Inference Error",
                "message": f"Computer vision analysis failed: {str(exc)}",
            }), 500

        if analysis_dict.get("requires_replacement"):
            return jsonify({
                "success": False,
                "error": "Invalid Vehicle Evidence",
                "message": (
                    f"Uploaded file '{target_img_path.name}' is flagged as {img_validation.get('status', 'invalid')} "
                    f"({img_validation.get('reason')}). Damage inspection cannot be performed on synthetic graphics or document renders. "
                    f"Please upload an authentic replacement vehicle photograph before running AI damage analysis."
                ),
                "validation": analysis_dict.get("validation", img_validation),
                "requires_replacement": True,
            }), 400

        if analysis_dict.get("analysis_status") == "failed" and analysis_dict.get("error"):
            return jsonify({
                "success": False,
                "error": "Inference Error",
                "message": f"Computer vision analysis failed: {analysis_dict.get('error')}",
                "analysis": analysis_dict,
            }), 500

        logger.info(
            f"Successfully completed vehicle damage analysis for {claim_id}: "
            f"{analysis_dict.get('total_detections', 0)} detections ({', '.join(analysis_dict.get('damage_categories', [])) or 'None'}) "
            f"in {analysis_dict.get('processing_time_ms', 0)}ms"
        )

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "analysis": analysis_dict,
        }), 200


@claims_bp.route("/claims/<claim_id>/damage-analysis", methods=["GET"])
def get_claim_damage_analysis(claim_id: str):
    """Retrieves the latest vehicle damage analysis for a claim."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to access damage analysis.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to access damage analysis for this claim.",
            }), 403

        latest_analysis = (
            db.query(VehicleDamageAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(VehicleDamageAnalysis.id))
            .first()
        )

        if not latest_analysis:
            return jsonify({
                "success": False,
                "error": "Not Analyzed",
                "message": "No vehicle damage analysis has been executed for this claim yet.",
                "analyzed": False,
            }), 404

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "analyzed": True,
            "analysis": latest_analysis.to_dict(),
        }), 200


@claims_bp.route("/claims/<claim_id>/damage-history", methods=["GET"])
def get_claim_damage_history(claim_id: str):
    """Retrieves all vehicle damage analysis runs for a claim."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to view damage history.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to view damage history for this claim.",
            }), 403

        analyses = (
            db.query(VehicleDamageAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(VehicleDamageAnalysis.id))
            .all()
        )

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "total_runs": len(analyses),
            "history": [a.to_dict() for a in analyses],
        }), 200


@claims_bp.route("/claims/<claim_id>/annotated-image", methods=["GET"])
def get_claim_annotated_image(claim_id: str):
    """Streams the AI-annotated vehicle damage photograph."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to access annotated image.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to access annotated image.",
            }), 403

        upload_base = Path(current_app.config["UPLOAD_FOLDER"])
        latest = (
            db.query(VehicleDamageAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(VehicleDamageAnalysis.id))
            .first()
        )

        annotated_path = None
        if latest and latest.annotated_image_path:
            candidate = upload_base / latest.annotated_image_path
            if candidate.exists():
                annotated_path = candidate

        if not annotated_path:
            # Check images directory on disk
            images_dir = upload_base / claim_id / "images"
            if images_dir.exists():
                annotated_files = sorted(list(images_dir.glob("annotated_replacement_vehicle_image_*")))
                if not annotated_files:
                    annotated_files = sorted(list(images_dir.glob("annotated_*")))
                if not annotated_files:
                    annotated_files = sorted(list(images_dir.glob("opencv_analysis_*")))
                if annotated_files:
                    annotated_path = annotated_files[-1]

        if not annotated_path or not annotated_path.exists():
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": "Annotated damage image not found. Please run damage analysis first.",
            }), 404

        return send_file(
            str(annotated_path),
            mimetype="image/jpeg",
            as_attachment=request.args.get("download") == "true",
            download_name=annotated_path.name,
        )


@claims_bp.route("/vision/status", methods=["GET"])
@claims_bp.route("/vision/metrics", methods=["GET"])
@claims_bp.route("/model/status", methods=["GET"])
@claims_bp.route("/phase5/metrics", methods=["GET"])
def get_vision_status():
    """Returns the operational status of the vehicle damage detection model and CarDD benchmark."""
    try:
        detector = VehicleDamageDetector.get_instance()
        eval_metrics = get_model_evaluation_metrics()
        model_avail = detector.is_model_available()
        classes = detector.class_names
        return jsonify({
            "success": True,
            "status": "ready" if model_avail else "fallback_ready",
            "model_available": model_avail,
            "detection_method": detector.detection_method,
            "model_name": detector.model_name,
            "model_version": detector.model_version,
            "model_path": str(detector.model_path) if detector.model_path else None,
            "device": detector.device,
            "dataset": "CarDD",
            "classes": classes,
            "evaluation_metrics": eval_metrics.get("overall_metrics"),
            "per_class_metrics": eval_metrics.get("per_class_metrics"),
            "latency_metrics": eval_metrics.get("latency_metrics"),
            "full_evaluation": eval_metrics,
        }), 200
    except Exception as exc:
        return jsonify({
            "success": False,
            "status": "error",
            "message": str(exc),
        }), 500


# =========================================================================
# Phase 6: NLP Claim Description Analysis & Chronological Extraction Routes
# =========================================================================

@claims_bp.route("/claims/<claim_id>/analyze-description", methods=["POST"])
@claims_bp.route("/claims/<claim_id>/analyze-nlp", methods=["POST"])
@csrf.exempt
def analyze_claim_description(claim_id: str):
    """Executes Phase 6 NLP analysis on the claimant accident narrative."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to analyze claim description.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to analyze description for this claim.",
            }), 403

        raw_desc = claim.claim_description or ""
        if not raw_desc.strip():
            return jsonify({
                "success": False,
                "error": "Empty Narrative",
                "message": "No claimant accident description has been provided for this claim.",
            }), 400

        # Gather extracted documents for cross-source consistency
        extracted_doc_rows = [
            r.to_dict() for r in db.query(ExtractedInformation).filter_by(claim_id=claim_id).all()
        ]
        claim_dict = claim.to_dict()

        # Run NLP analysis
        nlp_res = ClaimNLPService.analyze_claim_narrative(
            text=raw_desc,
            claim_id=claim_id,
            claimant_name=claim.claimant_name,
            extracted_doc_rows=extracted_doc_rows,
            claim_record=claim_dict,
        )

        # Store in database
        now_utc = datetime.now(timezone.utc)
        analysis_rec = ClaimNLPAnalysis(
            claim_id=claim_id,
            original_narrative=nlp_res["original_narrative"],
            normalized_narrative=nlp_res["normalized_narrative"],
            accident_type=nlp_res["accident_type"],
            accident_type_confidence=nlp_res["accident_type_confidence"],
            classification_method=nlp_res["classification_method"],
            classification_supporting_text=nlp_res["classification_supporting_text"],
            extracted_entities=json.dumps(nlp_res["entities"]),
            events_timeline=json.dumps(nlp_res["timeline"]),
            damage_descriptions=json.dumps(nlp_res["reported_damages"]),
            cross_consistency_findings=json.dumps(nlp_res["consistency"]),
            missing_information=json.dumps(nlp_res["missing_information"]),
            ambiguous_information=json.dumps(nlp_res["ambiguous_information"]),
            nlp_engine_version=nlp_res["engine_version"],
            processing_status=nlp_res["processing_status"],
            processing_time_ms=nlp_res["processing_time_ms"],
            created_at=now_utc,
            updated_at=now_utc,
        )
        db.add(analysis_rec)
        db.commit()

        # Update metadata.json if present
        upload_base = Path(current_app.config["UPLOAD_FOLDER"])
        claim_dir = upload_base / claim_id
        meta_file = claim_dir / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["latest_nlp_analysis"] = analysis_rec.to_dict()
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception as exc:
                logger.warning(f"Failed to update metadata.json with NLP analysis: {exc}")

        logger.info(
            f"Successfully completed NLP narrative analysis for {claim_id}: "
            f"Type={nlp_res['accident_type']} ({nlp_res['accident_type_confidence']:.2f}), "
            f"{nlp_res['total_entities']} entities, {nlp_res['total_events']} events, "
            f"{nlp_res['total_reported_damages']} damage items in {nlp_res['processing_time_ms']}ms"
        )

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "analysis": analysis_rec.to_dict(),
        }), 200


@claims_bp.route("/claims/<claim_id>/nlp-analysis", methods=["GET"])
def get_claim_nlp_analysis(claim_id: str):
    """Retrieves the latest NLP claim description analysis for a claim."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to access NLP analysis.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to access NLP analysis for this claim.",
            }), 403

        latest_analysis = (
            db.query(ClaimNLPAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(ClaimNLPAnalysis.id))
            .first()
        )

        if not latest_analysis:
            return jsonify({
                "success": False,
                "error": "Not Analyzed",
                "message": "No NLP narrative analysis has been executed for this claim yet.",
                "analyzed": False,
            }), 404

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "analyzed": True,
            "analysis": latest_analysis.to_dict(),
        }), 200


@claims_bp.route("/claims/<claim_id>/nlp-entities", methods=["GET"])
def get_claim_nlp_entities(claim_id: str):
    """Retrieves extracted domain entities from the claim narrative."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim or not can_user_access_claim(claim, user_id, user_role):
            return jsonify({"success": False, "error": "Unauthorized / Not Found"}), 404

        latest = (
            db.query(ClaimNLPAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(ClaimNLPAnalysis.id))
            .first()
        )
        if not latest:
            return jsonify({"success": False, "error": "Not Analyzed", "entities": []}), 404

        data = latest.to_dict()
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "total_entities": len(data.get("entities", [])),
            "entities": data.get("entities", []),
        }), 200


@claims_bp.route("/claims/<claim_id>/nlp-chronology", methods=["GET"])
def get_claim_nlp_chronology(claim_id: str):
    """Retrieves reconstructed accident chronological timeline."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim or not can_user_access_claim(claim, user_id, user_role):
            return jsonify({"success": False, "error": "Unauthorized / Not Found"}), 404

        latest = (
            db.query(ClaimNLPAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(ClaimNLPAnalysis.id))
            .first()
        )
        if not latest:
            return jsonify({"success": False, "error": "Not Analyzed", "timeline": []}), 404

        data = latest.to_dict()
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "total_steps": len(data.get("timeline", [])),
            "timeline": data.get("timeline", []),
            "missing_temporal_info": data.get("missing_information", []),
        }), 200


@claims_bp.route("/claims/<claim_id>/nlp-classification", methods=["GET"])
def get_claim_nlp_classification(claim_id: str):
    """Retrieves accident classification details."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim or not can_user_access_claim(claim, user_id, user_role):
            return jsonify({"success": False, "error": "Unauthorized / Not Found"}), 404

        latest = (
            db.query(ClaimNLPAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(ClaimNLPAnalysis.id))
            .first()
        )
        if not latest:
            return jsonify({"success": False, "error": "Not Analyzed"}), 404

        data = latest.to_dict()
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "accident_type": data.get("accident_type"),
            "confidence": data.get("accident_type_confidence"),
            "classification_method": data.get("classification_method"),
            "supporting_text": data.get("classification_supporting_text"),
        }), 200


@claims_bp.route("/claims/<claim_id>/nlp-consistency", methods=["GET"])
def get_claim_nlp_consistency(claim_id: str):
    """Retrieves cross-source consistency findings."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim or not can_user_access_claim(claim, user_id, user_role):
            return jsonify({"success": False, "error": "Unauthorized / Not Found"}), 404

        latest = (
            db.query(ClaimNLPAnalysis)
            .filter_by(claim_id=claim_id)
            .order_by(desc(ClaimNLPAnalysis.id))
            .first()
        )
        if not latest:
            return jsonify({"success": False, "error": "Not Analyzed"}), 404

        data = latest.to_dict()
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "consistency": data.get("consistency", {}),
        }), 200


# =========================================================================
# Phase 7: Cross-Source Verification & Intelligent Claim Validation Routes
# =========================================================================

@claims_bp.route("/claims/<claim_id>/verify-cross-source", methods=["POST"])
@csrf.exempt
def verify_claim_cross_source(claim_id: str):
    """Executes Phase 7 multi-source verification across policy, forms, OCR, NLP, and vision."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({
            "success": False,
            "error": "Invalid Claim ID format",
            "message": "Claim ID must follow format CLM-YYYYMMDD-XXXX.",
        }), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": f"Claim with ID '{claim_id}' was not found.",
            }), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required to perform cross-source verification.",
                }), 401
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "You do not have permission to verify this claim.",
            }), 403

    # Check for force flag
    force = False
    if request.is_json and request.json:
        force = bool(request.json.get("force", False))
    elif request.args.get("force"):
        force = request.args.get("force").lower() in ("true", "1", "yes")

    try:
        verification_result = ClaimVerificationService.verify_claim(claim_id=claim_id, force=force)
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "verification": verification_result,
        }), 200
    except VerificationPipelineError as v_err:
        return jsonify({
            "success": False,
            "claim_id": claim_id,
            "stage": v_err.stage,
            "error_code": v_err.error_code,
            "message": v_err.message,
            "retryable": v_err.retryable,
        }), 500
    except Exception as exc:
        logger.error(f"Unexpected error during cross-source verification for {claim_id}: {exc}", exc_info=True)
        return jsonify({
            "success": False,
            "claim_id": claim_id,
            "stage": "cross_source_verification",
            "error_code": "CROSS_SOURCE_VERIFICATION_ERROR",
            "message": "Cross-source verification could not be completed at this time.",
            "retryable": True,
        }), 500


@claims_bp.route("/claims/<claim_id>/verification", methods=["GET"])
def get_claim_verification(claim_id: str):
    """Retrieves the latest Phase 7 cross-source verification run for a claim."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({"success": False, "error": "Not Found"}), 404

        if not can_user_access_claim(claim, user_id, user_role):
            if not user_id:
                return jsonify({"success": False, "error": "Unauthorized"}), 401
            return jsonify({"success": False, "error": "Forbidden"}), 403

        if not claim.verification_runs:
            return jsonify({
                "success": False,
                "error": "Not Verified",
                "message": "Cross-source verification has not been executed for this claim yet.",
                "verified": False,
            }), 404

        latest_run = sorted(claim.verification_runs, key=lambda r: r.id)[-1]
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "verified": True,
            "verification": latest_run.to_dict(include_findings=True),
        }), 200


@claims_bp.route("/claims/<claim_id>/verification/findings", methods=["GET"])
def get_claim_verification_findings(claim_id: str):
    """Retrieves individual comparison findings with optional severity or status filtering."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim or not can_user_access_claim(claim, user_id, user_role):
            if not claim:
                return jsonify({"success": False, "error": "Not Found"}), 404
            return jsonify({"success": False, "error": "Unauthorized" if not user_id else "Forbidden"}), 401 if not user_id else 403

        if not claim.verification_runs:
            return jsonify({"success": False, "error": "Not Verified", "findings": []}), 404

        latest_run = sorted(claim.verification_runs, key=lambda r: r.id)[-1]
        findings = [f.to_dict() for f in latest_run.findings]

        # Optional filtering
        severity_filter = request.args.get("severity")
        status_filter = request.args.get("status")

        if severity_filter:
            findings = [f for f in findings if f.get("severity", "").upper() == severity_filter.upper()]
        if status_filter:
            findings = [f for f in findings if f.get("comparison_status", "").upper() == status_filter.upper()]

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "total_findings": len(findings),
            "findings": findings,
        }), 200


@claims_bp.route("/claims/<claim_id>/verification/summary", methods=["GET"])
def get_claim_verification_summary(claim_id: str):
    """Retrieves high-level verification metrics, consistency score, and review recommendations."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim or not can_user_access_claim(claim, user_id, user_role):
            if not claim:
                return jsonify({"success": False, "error": "Not Found"}), 404
            return jsonify({"success": False, "error": "Unauthorized" if not user_id else "Forbidden"}), 401 if not user_id else 403

        if not claim.verification_runs:
            return jsonify({"success": False, "error": "Not Verified"}), 404

        latest_run = sorted(claim.verification_runs, key=lambda r: r.id)[-1]
        data = latest_run.to_dict(include_findings=False)

        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "overall_status": data["overall_status"],
            "consistency_score": data["consistency_score"],
            "matched_comparisons": data["matched_comparisons"],
            "mismatched_comparisons": data["mismatched_comparisons"],
            "missing_evidence_count": data["missing_evidence_count"],
            "inconclusive_count": data["inconclusive_count"],
            "high_severity_count": data["high_severity_count"],
            "critical_severity_count": data["critical_severity_count"],
            "recommendations": data["recommendations"],
            "processing_time_ms": data["processing_time_ms"],
        }), 200


@claims_bp.route("/claims/<claim_id>/status", methods=["GET"])
def get_claim_task_status(claim_id: str):
    """Retrieves asynchronous processing status and stage progression for a claim."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({"success": False, "error": "Not Found", "message": "Claim not found"}), 404

        if not can_user_access_claim(claim, user_id, user_role):
            return jsonify({"success": False, "error": "Unauthorized" if not user_id else "Forbidden"}), 401 if not user_id else 403

    task_data = queue_manager.get_task_status(claim_id)
    if not task_data:
        # Fallback synthetic status for legacy claims or completed claims without explicit task record
        return jsonify({
            "success": True,
            "claim_id": claim_id,
            "task_id": f"synthetic-{claim_id}",
            "status": "completed" if claim.status in ("PROCESSED", "VERIFIED", "SUBMITTED") else claim.status.lower(),
            "stage": "COMPLETED" if claim.status in ("PROCESSED", "VERIFIED") else "INTAKE",
            "progress_percent": 100 if claim.status in ("PROCESSED", "VERIFIED") else 100,
            "error_message": None,
            "error_code": None,
            "result_metadata": None,
            "retry_count": 0,
            "max_retries": 3,
            "worker_id": "legacy_handler",
            "created_at": claim.created_at.isoformat() if claim.created_at else None,
            "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
            "completed_at": claim.updated_at.isoformat() if claim.updated_at else None,
        }), 200

    return jsonify({
        "success": True,
        "claim_id": claim_id,
        "task_id": task_data["task_id"],
        "status": task_data["status"].lower(),
        "stage": task_data["current_stage"],
        "progress_percent": task_data["progress_percent"],
        "error_message": task_data["error_message"],
        "error_code": task_data["error_code"],
        "result_metadata": task_data["result_metadata"],
        "retry_count": task_data["retry_count"],
        "max_retries": task_data["max_retries"],
        "worker_id": task_data["worker_id"],
        "created_at": task_data["created_at"],
        "updated_at": task_data["updated_at"],
        "completed_at": task_data["completed_at"],
    }), 200


@claims_bp.route("/claims/<claim_id>/retry-task", methods=["POST"])
def retry_claim_task(claim_id: str):
    """Manually re-enqueues a failed or stuck claim processing task."""
    if not is_valid_claim_id_format(claim_id):
        return jsonify({"success": False, "error": "Invalid Claim ID format"}), 400

    user_id = session.get("user_id")
    user_role = session.get("role")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        if not claim:
            return jsonify({"success": False, "error": "Not Found", "message": "Claim not found"}), 404

        if not can_user_access_claim(claim, user_id, user_role):
            return jsonify({"success": False, "error": "Unauthorized" if not user_id else "Forbidden"}), 401 if not user_id else 403

    task, is_new = queue_manager.enqueue_claim_task(claim_id=claim_id, user_id=user_id, sync=False)
    return jsonify({
        "success": True,
        "claim_id": claim_id,
        "task_id": task.task_id if hasattr(task, "task_id") else task.get("task_id"),
        "status": task.status.lower() if hasattr(task, "status") else "queued",
        "message": "Task re-enqueued successfully",
    }), 202

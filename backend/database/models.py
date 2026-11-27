"""SQLAlchemy ORM models for ClaimSense AI (Phase 3 & Phase 5)."""
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """User account entity with role-based access control and hashed passwords."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=False)
    role = Column(String(20), default="user", nullable=False)  # 'user', 'assessor', 'admin'
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    claims = relationship("Claim", back_populates="user", lazy="select")

    def set_password(self, password: str) -> None:
        """Securely hash and store password using Werkzeug."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify plain password against stored Werkzeug hash."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize user data safely without exposing password hashes."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Claim(Base):
    """Central Claim entity with unique Claim ID and indexed policy number."""
    __tablename__ = "claims"

    claim_id = Column(String(32), primary_key=True, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    claimant_name = Column(String(120), nullable=False)
    policy_number = Column(String(64), nullable=False, index=True)
    vehicle_number = Column(String(32), nullable=False, index=True)
    accident_date = Column(String(32), nullable=False)
    incident_location = Column(String(256), nullable=True)
    claim_description = Column(Text, nullable=False)
    status = Column(String(32), default="SUBMITTED", nullable=False)
    final_verdict = Column(String(32), nullable=True, index=True)  # ACCEPTED, NOT_ACCEPTED, MANUAL_REVIEW
    decision_reason = Column(Text, nullable=True)
    fraud_risk_level = Column(String(32), nullable=True)  # LOW, MEDIUM, HIGH
    decision_timestamp = Column(DateTime, nullable=True)
    verdict_details = Column(Text, nullable=True)  # JSON payload with checks & verification summary
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="claims")
    documents = relationship("Document", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    images = relationship("ClaimImage", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    extracted_info = relationship("ExtractedInformation", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    image_analyses = relationship("ImageAnalysis", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    vehicle_damage_analyses = relationship("VehicleDamageAnalysis", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    nlp_analyses = relationship("ClaimNLPAnalysis", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    verification_results = relationship("VerificationResult", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    verification_runs = relationship("ClaimVerificationRun", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    verification_findings = relationship("VerificationFinding", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    risk_assessments = relationship("RiskAssessment", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    reports = relationship("Report", back_populates="claim", cascade="all, delete-orphan", lazy="select")

    def get_final_verdict_dict(self) -> Optional[Dict[str, Any]]:
        """Returns structured Final Claim Verdict payload if persisted, else None."""
        if not self.final_verdict:
            return None
        details: Dict[str, Any] = {}
        if self.verdict_details:
            try:
                details = json.loads(self.verdict_details)
            except Exception:
                details = {}
        return {
            "final_verdict": self.final_verdict,
            "decision_reason": self.decision_reason,
            "fraud_risk_level": self.fraud_risk_level or details.get("fraud_risk_level") or "MEDIUM",
            "fraud_risk_score": details.get("fraud_risk_score"),
            "verification_summary": details.get("verification_summary", {}),
            "passed_checks": details.get("passed_checks", []),
            "failed_checks": details.get("failed_checks", []),
            "inconclusive_checks": details.get("inconclusive_checks", []),
            "manual_review_required": details.get("manual_review_required", self.final_verdict == "MANUAL_REVIEW"),
            "manual_review_remarks": details.get("manual_review_remarks", []),
            "risk_reasons": details.get("risk_reasons", []),
            "decision_timestamp": (
                self.decision_timestamp.isoformat()
                if self.decision_timestamp
                else details.get("decision_timestamp")
            ),
        }

    def to_dict(self, include_evidence: bool = True) -> Dict[str, Any]:
        """Serializes claim entity to dictionary representation."""
        verdict_obj = self.get_final_verdict_dict()
        data = {
            "claim_id": self.claim_id,
            "user_id": self.user_id,
            "claimant_name": self.claimant_name,
            "policy_number": self.policy_number,
            "vehicle_number": self.vehicle_number,
            "accident_date": self.accident_date,
            "incident_location": self.incident_location,
            "claim_description": self.claim_description,
            "status": self.status,
            "final_verdict": self.final_verdict,
            "decision_reason": self.decision_reason,
            "fraud_risk_level": self.fraud_risk_level,
            "decision_timestamp": self.decision_timestamp.isoformat() if self.decision_timestamp else None,
            "verdict": verdict_obj,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_evidence:
            data["documents"] = [doc.to_dict() for doc in self.documents]
            data["images"] = [img.to_dict() for img in self.images]

            # Construct backward-compatible 'files' dictionary format matching Phase 2
            files_dict = {}
            type_mapping = {
                "POLICY_DOCUMENT": "policy_document",
                "CLAIM_FORM": "claim_form",
                "INVOICE": "invoice_document",
            }
            for doc in self.documents:
                key = type_mapping.get(doc.document_type, doc.document_type.lower())
                files_dict[key] = {
                    "original_name": doc.original_filename,
                    "saved_as": doc.stored_filename,
                    "relative_path": doc.file_path,
                    "size_bytes": doc.file_size,
                }
            archived = []
            for img in sorted(self.images, key=lambda i: i.image_id):
                if "vehicle_image" in files_dict:
                    archived.append(files_dict["vehicle_image"])
                files_dict["vehicle_image"] = {
                    "original_name": img.original_filename,
                    "saved_as": img.stored_filename,
                    "relative_path": img.file_path,
                    "size_bytes": img.file_size,
                }
            if archived:
                data["archived_images"] = archived
            data["files"] = files_dict
            data["files_count"] = len(self.documents) + len(self.images)

            if self.vehicle_damage_analyses:
                latest_analysis = sorted(self.vehicle_damage_analyses, key=lambda a: a.id)[-1]
                data["damage_analysis"] = latest_analysis.to_dict()
            else:
                data["damage_analysis"] = None

            if self.nlp_analyses:
                latest_nlp = sorted(self.nlp_analyses, key=lambda a: a.id)[-1]
                data["nlp_analysis"] = latest_nlp.to_dict()
            else:
                data["nlp_analysis"] = None

            if self.verification_runs:
                latest_verif = sorted(self.verification_runs, key=lambda r: r.id)[-1]
                verif_dict = latest_verif.to_dict(include_findings=True)
                if verdict_obj and "final_verdict" not in verif_dict:
                    verif_dict["final_verdict"] = verdict_obj
                data["verification"] = verif_dict
            else:
                data["verification"] = None

        return data


class Document(Base):
    """Submitted evidentiary documents (Policy Schedule, Claim Form, Invoice)."""
    __tablename__ = "documents"

    document_id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    document_type = Column(String(64), nullable=False)  # POLICY_DOCUMENT, CLAIM_FORM, INVOICE, OTHER
    file_path = Column(String(512), nullable=False)
    original_filename = Column(String(256), nullable=False)
    stored_filename = Column(String(256), nullable=False)
    file_extension = Column(String(16), nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    claim = relationship("Claim", back_populates="documents")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "claim_id": self.claim_id,
            "document_type": self.document_type,
            "file_path": self.file_path,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "file_extension": self.file_extension,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ClaimImage(Base):
    """Submitted photographic evidence of damaged vehicle."""
    __tablename__ = "claim_images"

    image_id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    image_type = Column(String(64), default="VEHICLE_ACCIDENT", nullable=False)
    file_path = Column(String(512), nullable=False)
    original_filename = Column(String(256), nullable=False)
    stored_filename = Column(String(256), nullable=False)
    file_extension = Column(String(16), nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    claim = relationship("Claim", back_populates="images")

    @property
    def id(self) -> int:
        return self.image_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "claim_id": self.claim_id,
            "image_type": self.image_type,
            "file_path": self.file_path,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "file_extension": self.file_extension,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExtractedInformation(Base):
    """Phase 4 structured extraction storage with evidence and status metadata."""
    __tablename__ = "extracted_information"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    field_name = Column(String(128), nullable=False)
    field_value = Column(Text, nullable=True)
    field_status = Column(String(32), nullable=True, default="not_present")
    source = Column(String(64), nullable=False)  # policy_document, claim_form, invoice
    source_filename = Column(String(255), nullable=True)
    page_number = Column(Integer, nullable=True)
    extraction_method = Column(String(64), nullable=True)
    supporting_text = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    evaluation_metadata = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    claim = relationship("Claim", back_populates="extracted_info")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "field_name": self.field_name,
            "field_value": self.field_value,
            "field_status": self.field_status,
            "source": self.source,
            "source_filename": self.source_filename,
            "page_number": self.page_number,
            "extraction_method": self.extraction_method,
            "supporting_text": self.supporting_text,
            "confidence_score": self.confidence_score,
            "error_message": self.error_message,
            "evaluation_metadata": self.evaluation_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ImageAnalysis(Base):
    """Future schema for Phase 5 (Computer Vision vehicle damage inspection)."""
    __tablename__ = "image_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("claim_images.image_id"), nullable=True)
    detected_damage = Column(String(128), nullable=True)
    damage_location = Column(String(128), nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    claim = relationship("Claim", back_populates="image_analyses")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "image_id": self.image_id,
            "detected_damage": self.detected_damage,
            "damage_location": self.damage_location,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VehicleDamageAnalysis(Base):
    """Phase 5 Vehicle damage detection results from fine-tuned YOLOv8 on CarDD."""
    __tablename__ = "vehicle_damage_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("claim_images.image_id"), nullable=True)
    image_hash = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)
    original_image_path = Column(String(512), nullable=True, default="")
    annotated_image_path = Column(String(512), nullable=True)
    model_name = Column(String(64), default="YOLOv8n-CarDD", nullable=False)
    model_version = Column(String(32), default="v1.0", nullable=False)
    total_detections = Column(Integer, default=0, nullable=False)
    total_damages_detected = Column(Integer, default=0, nullable=True)
    damage_categories = Column(Text, nullable=True, default="[]")
    detected_categories = Column(Text, nullable=True, default="[]")
    highest_confidence = Column(Float, nullable=True, default=0.0)
    max_confidence = Column(Float, nullable=True, default=0.0)
    average_confidence = Column(Float, nullable=True, default=0.0)
    analysis_status = Column(String(32), default="completed", nullable=True)
    detection_method = Column(String(64), default="YOLOv8", nullable=True)
    model_available = Column(Boolean, default=True, nullable=True)
    opencv_observations = Column(Text, nullable=True)
    processing_time_ms = Column(Float, nullable=True, default=0.0)
    inference_time_ms = Column(Float, nullable=True, default=0.0)
    device = Column(String(32), default="cpu", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=True)

    claim = relationship("Claim", back_populates="vehicle_damage_analyses")
    detections = relationship("VehicleDamageDetection", back_populates="analysis", cascade="all, delete-orphan", lazy="select")

    def to_dict(self) -> Dict[str, Any]:
        try:
            cats = json.loads(self.damage_categories) if self.damage_categories else []
        except Exception:
            cats = [c.strip() for c in (self.damage_categories or "").split(",") if c.strip()]

        try:
            obs = json.loads(self.opencv_observations) if self.opencv_observations else None
        except Exception:
            obs = None

        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "image_id": self.image_id,
            "image_hash": self.image_hash,
            "image_path": self.image_path,
            "annotated_image_path": self.annotated_image_path,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "detection_method": self.detection_method or "YOLOv8",
            "model_available": self.model_available if self.model_available is not None else True,
            "total_detections": self.total_detections,
            "damage_categories": cats,
            "highest_confidence": round(self.highest_confidence, 4) if self.highest_confidence is not None else 0.0,
            "average_confidence": round(self.average_confidence, 4) if self.average_confidence is not None else 0.0,
            "processing_time_ms": round(self.processing_time_ms, 2) if self.processing_time_ms is not None else 0.0,
            "device": self.device,
            "analysis_status": self.analysis_status or "completed",
            "opencv_observations": obs,
            "detections": [d.to_dict() for d in self.detections] if self.detections else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VehicleDamageDetection(Base):
    """Phase 5 Individual detected damage bounding boxes, confidence, and spatial regions."""
    __tablename__ = "vehicle_damage_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("vehicle_damage_analyses.id"), nullable=False, index=True)
    detection_index = Column(Integer, nullable=False)
    category = Column(String(64), nullable=False)
    confidence = Column(Float, nullable=False)
    bbox_x1 = Column(Float, nullable=False)
    bbox_y1 = Column(Float, nullable=False)
    bbox_x2 = Column(Float, nullable=False)
    bbox_y2 = Column(Float, nullable=False)
    location_region = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    analysis = relationship("VehicleDamageAnalysis", back_populates="detections")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "analysis_id": self.analysis_id,
            "detection_index": self.detection_index,
            "category": self.category,
            "confidence": round(self.confidence, 4),
            "confidence_percentage": round(self.confidence * 100, 1),
            "bbox": [
                round(self.bbox_x1, 1),
                round(self.bbox_y1, 1),
                round(self.bbox_x2, 1),
                round(self.bbox_y2, 1),
            ],
            "location_region": self.location_region or "unspecified",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



class ClaimNLPAnalysis(Base):
    """Phase 6 Claimant Narrative NLP Analysis, Entity Extraction, and Chronology."""
    __tablename__ = "claim_nlp_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    original_narrative = Column(Text, nullable=False)
    normalized_narrative = Column(Text, nullable=True)
    accident_type = Column(String(64), nullable=False)
    accident_type_confidence = Column(Float, nullable=False, default=0.0)
    classification_method = Column(String(64), nullable=False, default="Linguistic Pattern Matching")
    classification_supporting_text = Column(Text, nullable=True)
    extracted_entities = Column(Text, nullable=True)
    events_timeline = Column(Text, nullable=True)
    damage_descriptions = Column(Text, nullable=True)
    cross_consistency_findings = Column(Text, nullable=True)
    missing_information = Column(Text, nullable=True)
    ambiguous_information = Column(Text, nullable=True)
    nlp_engine_version = Column(String(32), default="1.0.0", nullable=False)
    processing_status = Column(String(32), default="completed", nullable=False)
    processing_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=True)

    claim = relationship("Claim", back_populates="nlp_analyses")

    def to_dict(self) -> Dict[str, Any]:
        def safe_json(val, default):
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "original_narrative": self.original_narrative,
            "normalized_narrative": self.normalized_narrative,
            "accident_type": self.accident_type,
            "accident_type_confidence": round(self.accident_type_confidence, 2) if self.accident_type_confidence is not None else 0.0,
            "classification_method": self.classification_method,
            "classification_supporting_text": self.classification_supporting_text,
            "entities": safe_json(self.extracted_entities, []),
            "timeline": safe_json(self.events_timeline, []),
            "reported_damages": safe_json(self.damage_descriptions, []),
            "consistency": safe_json(self.cross_consistency_findings, {}),
            "missing_information": safe_json(self.missing_information, []),
            "ambiguous_information": safe_json(self.ambiguous_information, []),
            "engine_version": self.nlp_engine_version,
            "processing_status": self.processing_status,
            "processing_time_ms": round(self.processing_time_ms, 2) if self.processing_time_ms is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class VerificationResult(Base):
    """Future schema for Phase 7 (Cross-source consistency rule engine)."""
    __tablename__ = "verification_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    field = Column(String(128), nullable=False)
    source_1 = Column(String(64), nullable=False)
    source_2 = Column(String(64), nullable=False)
    value_1 = Column(Text, nullable=True)
    value_2 = Column(Text, nullable=True)
    result = Column(String(32), nullable=False)  # CONSISTENT, MINOR_MISMATCH, MAJOR_MISMATCH, MISSING_INFORMATION
    explanation = Column(Text, nullable=True)
    severity = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    claim = relationship("Claim", back_populates="verification_results")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "field": self.field,
            "source_1": self.source_1,
            "source_2": self.source_2,
            "value_1": self.value_1,
            "value_2": self.value_2,
            "result": self.result,
            "explanation": self.explanation,
            "severity": self.severity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ClaimVerificationRun(Base):
    """Phase 7: Master verification run recording overall consistency score, summary, and status."""
    __tablename__ = "claim_verification_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=True, index=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    engine_version = Column(String(32), default="1.0.0", nullable=False)
    overall_status = Column(String(32), default="CONSISTENT", nullable=False)  # CONSISTENT, REVIEW_REQUIRED, INSUFFICIENT_EVIDENCE
    consistency_score = Column(Float, default=100.0, nullable=False)
    total_comparisons = Column(Integer, default=0, nullable=False)
    matched_comparisons = Column(Integer, default=0, nullable=False)
    mismatched_comparisons = Column(Integer, default=0, nullable=False)
    missing_evidence_count = Column(Integer, default=0, nullable=False)
    inconclusive_count = Column(Integer, default=0, nullable=False)
    high_severity_count = Column(Integer, default=0, nullable=False)
    critical_severity_count = Column(Integer, default=0, nullable=False)
    summary = Column(Text, nullable=True)  # JSON summary
    recommendations = Column(Text, nullable=True)  # JSON list of recommendations
    processing_status = Column(String(32), default="completed", nullable=False)
    processing_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=True)

    claim = relationship("Claim", back_populates="verification_runs")
    findings = relationship("VerificationFinding", back_populates="run", cascade="all, delete-orphan", lazy="select")

    def to_dict(self, include_findings: bool = True) -> Dict[str, Any]:
        def safe_json(val, default):
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        summary_obj = safe_json(self.summary, {})
        cov_pct = summary_obj.get("evidence_coverage_percentage")
        if cov_pct is None and self.total_comparisons:
            evaluated_count = (self.matched_comparisons or 0) + (self.mismatched_comparisons or 0)
            cov_pct = round((evaluated_count / self.total_comparisons) * 100.0, 1)

        data = {
            "id": self.id,
            "run_id": self.run_id or (f"VRUN-{self.id}" if self.id else None),
            "claim_id": self.claim_id,
            "engine_version": self.engine_version,
            "overall_status": self.overall_status,
            "consistency_score": round(self.consistency_score, 1) if self.consistency_score is not None else 0.0,
            "evidence_coverage_percentage": cov_pct if cov_pct is not None else 100.0,
            "total_comparisons": self.total_comparisons,
            "matched_comparisons": self.matched_comparisons,
            "mismatched_comparisons": self.mismatched_comparisons,
            "missing_evidence_count": self.missing_evidence_count,
            "inconclusive_count": self.inconclusive_count,
            "high_severity_count": self.high_severity_count,
            "critical_severity_count": self.critical_severity_count,
            "summary": summary_obj,
            "recommendations": safe_json(self.recommendations, []),
            "processing_status": self.processing_status,
            "processing_time_ms": round(self.processing_time_ms, 2) if self.processing_time_ms is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_findings:
            data["findings"] = [f.to_dict() for f in self.findings] if self.findings else []
        return data


class VerificationFinding(Base):
    """Phase 7: Individual structured comparison finding between evidence sources."""
    __tablename__ = "verification_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("claim_verification_runs.id"), nullable=True, index=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    comparison_id = Column(String(64), nullable=False, index=True)
    source_a = Column(String(64), nullable=False)
    source_b = Column(String(64), nullable=False)
    field_name = Column(String(128), nullable=False)
    original_value_a = Column(Text, nullable=True)
    original_value_b = Column(Text, nullable=True)
    normalized_value_a = Column(Text, nullable=True)
    normalized_value_b = Column(Text, nullable=True)
    comparison_status = Column(String(32), nullable=False)  # MATCH, MISMATCH, MISSING_IN_SOURCE, INCONCLUSIVE, NOT_VISUALLY_CONFIRMED, VISUAL_ONLY_FINDING, POTENTIAL_DISCREPANCY
    severity = Column(String(32), nullable=False, default="LOW")  # LOW, MEDIUM, HIGH, CRITICAL
    confidence = Column(Float, nullable=False, default=1.0)
    explanation = Column(Text, nullable=True)
    evidence_references = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    run = relationship("ClaimVerificationRun", back_populates="findings")
    claim = relationship("Claim", back_populates="verification_findings")

    def to_dict(self) -> Dict[str, Any]:
        def safe_json(val, default):
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        return {
            "id": self.id,
            "run_id": self.run_id,
            "claim_id": self.claim_id,
            "comparison_id": self.comparison_id,
            "source_a": self.source_a,
            "source_b": self.source_b,
            "field_name": self.field_name,
            "original_value_a": self.original_value_a,
            "original_value_b": self.original_value_b,
            "normalized_value_a": self.normalized_value_a,
            "normalized_value_b": self.normalized_value_b,
            "comparison_status": self.comparison_status,
            "severity": self.severity,
            "confidence": round(self.confidence, 2) if self.confidence is not None else 1.0,
            "explanation": self.explanation,
            "evidence_references": safe_json(self.evidence_references, {}),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RiskAssessment(Base):
    """Future schema for Phase 8 (Explainable weighted fraud-risk scoring)."""
    __tablename__ = "risk_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    risk_level = Column(String(32), nullable=False)  # LOW, MEDIUM, HIGH
    risk_score = Column(Float, nullable=False)
    reasons = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    claim = relationship("Claim", back_populates="risk_assessments")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "reasons": self.reasons,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Report(Base):
    """Future schema for Phase 10 (Assessor verification audit reports)."""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(String(32), ForeignKey("claims.claim_id"), nullable=False, index=True)
    report_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    claim = relationship("Claim", back_populates="reports")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "report_path": self.report_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

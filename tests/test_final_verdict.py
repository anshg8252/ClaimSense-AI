"""Comprehensive automated tests for the Final Claim Verdict / Decision Engine.

Covers:
1. Clean corroborated checks + LOW fraud risk -> ACCEPTED
2. Critical/high established contradiction -> NOT_ACCEPTED with specific reason
3. Missing mandatory evidence -> MANUAL_REVIEW
4. Inconclusive OCR/document extraction -> MANUAL_REVIEW
5. High fraud risk without established hard contradiction -> MANUAL_REVIEW (no auto-reject)
6. Low fraud risk with critical verification failure -> NOT_ACCEPTED (no auto-accept)
7. Legacy claims with final_verdict=None retrieved cleanly without errors
8. Full DB persistence, API routes (/verdict, /verify-cross-source, /verification,
   /verification/summary, /claims/<id>, /policy, /search, /my-claims, JSON & PDF receipts),
   and async pipeline (execute_claim_processing_pipeline) persistence
9. Frontend HTML/CSS/JS rendering verification for all verdict states + legacy fallback
"""

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import create_app
from backend.config import Config
from backend.database.db import get_db_session
from backend.database.models import (
    Claim,
    ClaimImage,
    ClaimNLPAnalysis,
    Document,
    ExtractedInformation,
    RiskAssessment,
    User,
    VehicleDamageAnalysis,
)
from backend.services.receipt import (
    generate_claim_receipt_pdf,
    generate_document_intelligence_report_pdf,
)
from backend.services.risk import FraudRiskAssessor
from backend.services.verification.rules import (
    OVERALL_CONSISTENT,
    OVERALL_INSUFFICIENT_EVIDENCE,
    OVERALL_REVIEW_REQUIRED,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    STATUS_EXTRACTION_ERROR,
    STATUS_INCONCLUSIVE,
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_MISSING_IN_SOURCE,
    STATUS_NEEDS_REVIEW,
)
from backend.services.verification.verdict import (
    FinalVerdictEngine,
    VERDICT_ACCEPTED,
    VERDICT_MANUAL_REVIEW,
    VERDICT_NOT_ACCEPTED,
)


# ---------------------------------------------------------------------------
# Helpers for deterministic unit-test payloads
# ---------------------------------------------------------------------------

def _complete_claim_record():
    return {
        "claim_id": "CLM-20261127-9001",
        "documents": [
            {"document_type": "POLICY_DOCUMENT", "original_filename": "policy.pdf"},
            {"document_type": "CLAIM_FORM", "original_filename": "claim_form.pdf"},
            {"document_type": "INVOICE", "original_filename": "invoice.pdf"},
        ],
        "images": [{"image_id": 1, "original_filename": "front_bumper.jpg"}],
    }


def _complete_ocr_rows():
    return [
        {
            "source": "policy_document",
            "source_filename": "policy.pdf",
            "field_name": "policy_number",
            "field_value": "POL-2026-001",
            "status": "extracted",
        },
        {
            "source": "claim_form",
            "source_filename": "claim_form.pdf",
            "field_name": "claimant_name",
            "field_value": "Aarav Mehta",
            "status": "extracted",
        },
        {
            "source": "invoice",
            "source_filename": "invoice.pdf",
            "field_name": "total_amount",
            "field_value": "45000",
            "status": "extracted",
        },
    ]


def _clean_vision_analysis():
    return {
        "analysis_status": "completed",
        "detection_method": "yolov8",
        "model_available": True,
        "requires_replacement": False,
        "total_detections": 2,
    }


def _matched_findings(count=4):
    fields = [
        ("CMP_01", "Policy Number", "POL-2026-001", SEVERITY_LOW),
        ("CMP_02", "Vehicle Registration", "MH12AB1234", SEVERITY_LOW),
        ("CMP_03", "Claimant Name", "Aarav Mehta", SEVERITY_LOW),
        ("CMP_04", "Accident Date", "2026-11-20", SEVERITY_LOW),
        ("CMP_05", "Claim Amount", "45000", SEVERITY_LOW),
    ]
    return [
        {
            "comparison_id": cid,
            "field_name": fname,
            "source_a": "Claim Intake",
            "source_b": "Policy Document OCR",
            "source_a_value": val,
            "source_b_value": val,
            "comparison_status": STATUS_MATCH,
            "severity": sev,
            "explanation": f"{fname} verified across sources.",
        }
        for cid, fname, val, sev in fields[:count]
    ]


# ---------------------------------------------------------------------------
# Unit tests: FraudRiskAssessor & FinalVerdictEngine (Scenarios 1 - 6)
# ---------------------------------------------------------------------------

def test_verdict_accepted_when_all_critical_checks_pass_and_low_risk():
    """Scenario 1: Clean evidence + matched checks + LOW risk => ACCEPTED."""
    verif = {
        "overall_status": OVERALL_CONSISTENT,
        "consistency_score": 96.5,
        "evidence_coverage_percentage": 100.0,
        "total_comparisons": 4,
        "matched_comparisons": 4,
        "mismatched_comparisons": 0,
        "missing_evidence_count": 0,
        "inconclusive_count": 0,
        "high_severity_count": 0,
        "critical_severity_count": 0,
        "findings": _matched_findings(4),
    }

    result = FinalVerdictEngine.evaluate(
        verification_result=verif,
        claim_record=_complete_claim_record(),
        extracted_doc_rows=_complete_ocr_rows(),
        vision_analysis=_clean_vision_analysis(),
    )

    assert result["final_verdict"] == VERDICT_ACCEPTED
    assert result["fraud_risk_level"] == "LOW"
    assert result["manual_review_required"] is False
    assert result["failed_checks"] == []
    assert result["inconclusive_checks"] == []
    assert len(result["passed_checks"]) == 4
    assert "ACCEPTED" in result["decision_reason"]


def test_verdict_not_accepted_on_established_critical_contradiction():
    """Scenario 2: Critical/high verification contradiction => NOT_ACCEPTED."""
    findings = _matched_findings(3) + [
        {
            "comparison_id": "CMP_POLICY",
            "field_name": "Policy Number",
            "source_a": "Claim Intake",
            "source_b": "Policy Schedule OCR",
            "source_a_value": "POL-2026-001",
            "source_b_value": "POL-9999-999",
            "comparison_status": STATUS_MISMATCH,
            "severity": SEVERITY_CRITICAL,
            "explanation": "Policy number in intake contradicts uploaded policy document.",
        }
    ]
    verif = {
        "overall_status": OVERALL_REVIEW_REQUIRED,
        "consistency_score": 45.0,
        "evidence_coverage_percentage": 100.0,
        "total_comparisons": 4,
        "matched_comparisons": 3,
        "mismatched_comparisons": 1,
        "missing_evidence_count": 0,
        "inconclusive_count": 0,
        "high_severity_count": 0,
        "critical_severity_count": 1,
        "findings": findings,
    }

    result = FinalVerdictEngine.evaluate(
        verification_result=verif,
        claim_record=_complete_claim_record(),
        extracted_doc_rows=_complete_ocr_rows(),
        vision_analysis=_clean_vision_analysis(),
    )

    assert result["final_verdict"] == VERDICT_NOT_ACCEPTED
    assert result["manual_review_required"] is False
    assert len(result["failed_checks"]) == 1
    assert "Policy Number" in result["decision_reason"]
    assert "NOT_ACCEPTED" in result["decision_reason"]


def test_verdict_manual_review_on_missing_mandatory_evidence():
    """Scenario 3: Missing mandatory evidence => MANUAL_REVIEW."""
    incomplete_claim = {
        "claim_id": "CLM-20261127-9002",
        "documents": [
            {"document_type": "POLICY_DOCUMENT", "original_filename": "policy.pdf"},
        ],
        "images": [{"image_id": 1, "original_filename": "photo.jpg"}],
    }
    findings = _matched_findings(3) + [
        {
            "comparison_id": "CMP_INV",
            "field_name": "Repair Invoice Amount",
            "source_a": "Claim Intake",
            "source_b": "Repair Invoice OCR",
            "comparison_status": STATUS_MISSING_IN_SOURCE,
            "severity": SEVERITY_HIGH,
            "explanation": "Repair invoice document was not provided.",
        }
    ]
    verif = {
        "overall_status": OVERALL_INSUFFICIENT_EVIDENCE,
        "consistency_score": 82.0,
        "evidence_coverage_percentage": 75.0,
        "total_comparisons": 4,
        "matched_comparisons": 3,
        "mismatched_comparisons": 0,
        "missing_evidence_count": 1,
        "inconclusive_count": 0,
        "findings": findings,
    }

    result = FinalVerdictEngine.evaluate(
        verification_result=verif,
        claim_record=incomplete_claim,
        extracted_doc_rows=_complete_ocr_rows()[:1],
        vision_analysis=_clean_vision_analysis(),
    )

    assert result["final_verdict"] == VERDICT_MANUAL_REVIEW
    assert result["manual_review_required"] is True
    assert len(result["inconclusive_checks"]) >= 1
    assert len(result["manual_review_remarks"]) >= 1


def test_verdict_manual_review_on_inconclusive_ocr():
    """Scenario 4: Inconclusive OCR/document extraction => MANUAL_REVIEW."""
    ocr_with_errors = _complete_ocr_rows()[:2] + [
        {
            "source": "invoice",
            "source_filename": "invoice.pdf",
            "field_name": "total_amount",
            "field_value": "",
            "status": "extraction_error",
            "error_message": "OCR failed to extract readable amount",
        }
    ]
    findings = _matched_findings(3) + [
        {
            "comparison_id": "CMP_OCR",
            "field_name": "Invoice Total",
            "source_a": "Claim Intake",
            "source_b": "Invoice OCR",
            "comparison_status": STATUS_INCONCLUSIVE,
            "severity": SEVERITY_MEDIUM,
            "explanation": "Blurred invoice scan prevents reliable extraction.",
        }
    ]
    verif = {
        "overall_status": OVERALL_REVIEW_REQUIRED,
        "consistency_score": 85.0,
        "evidence_coverage_percentage": 80.0,
        "total_comparisons": 4,
        "matched_comparisons": 3,
        "mismatched_comparisons": 0,
        "missing_evidence_count": 0,
        "inconclusive_count": 1,
        "findings": findings,
    }

    result = FinalVerdictEngine.evaluate(
        verification_result=verif,
        claim_record=_complete_claim_record(),
        extracted_doc_rows=ocr_with_errors,
        vision_analysis=_clean_vision_analysis(),
    )

    assert result["final_verdict"] == VERDICT_MANUAL_REVIEW
    assert result["manual_review_required"] is True
    assert any("OCR" in c["check"] or "Invoice" in c["check"] for c in result["inconclusive_checks"])


def test_verdict_manual_review_on_high_fraud_risk_without_hard_contradiction():
    """Scenario 5: High fraud risk + inconclusive/ambiguous evidence (no MISMATCH) => MANUAL_REVIEW (never auto-reject)."""
    findings = [
        {
            "comparison_id": "CMP_01",
            "field_name": "Policy Number",
            "comparison_status": STATUS_MATCH,
            "severity": SEVERITY_LOW,
            "explanation": "Matched.",
        },
        {
            "comparison_id": "CMP_02",
            "field_name": "Damage Description",
            "comparison_status": STATUS_INCONCLUSIVE,
            "severity": SEVERITY_HIGH,
            "explanation": "Ambiguous visual corroboration.",
        },
        {
            "comparison_id": "CMP_03",
            "field_name": "Invoice Breakdown",
            "comparison_status": STATUS_NEEDS_REVIEW,
            "severity": SEVERITY_MEDIUM,
            "explanation": "Itemized breakdown needs manual check.",
        },
    ]
    verif = {
        "overall_status": OVERALL_REVIEW_REQUIRED,
        "consistency_score": 68.0,
        "evidence_coverage_percentage": 60.0,
        "total_comparisons": 3,
        "matched_comparisons": 1,
        "mismatched_comparisons": 0,
        "missing_evidence_count": 1,
        "inconclusive_count": 1,
        "findings": findings,
    }
    high_risk_payload = {
        "risk_level": "HIGH",
        "risk_score": 78.0,
        "reasons": ["High risk due to multiple ambiguous visual and billing indicators."],
    }

    result = FinalVerdictEngine.evaluate(
        verification_result=verif,
        risk_assessment=high_risk_payload,
        claim_record=_complete_claim_record(),
        extracted_doc_rows=_complete_ocr_rows(),
        vision_analysis=_clean_vision_analysis(),
    )

    assert result["fraud_risk_level"] == "HIGH"
    assert result["final_verdict"] == VERDICT_MANUAL_REVIEW
    assert result["manual_review_required"] is True
    assert result["failed_checks"] == []


def test_verdict_not_accepted_even_with_low_fraud_risk_when_critical_check_failed():
    """Scenario 6: Low fraud risk + failed critical check => NOT_ACCEPTED (never auto-accept)."""
    findings = _matched_findings(3) + [
        {
            "comparison_id": "CMP_VEH",
            "field_name": "Vehicle Registration",
            "source_a": "Claim Intake",
            "source_b": "Policy Document",
            "source_a_value": "MH12AB1234",
            "source_b_value": "DL01ZZ9999",
            "comparison_status": STATUS_MISMATCH,
            "severity": SEVERITY_HIGH,
            "explanation": "Vehicle plate contradicts insured vehicle on policy.",
        }
    ]
    verif = {
        "overall_status": OVERALL_REVIEW_REQUIRED,
        "consistency_score": 75.0,
        "evidence_coverage_percentage": 100.0,
        "total_comparisons": 4,
        "matched_comparisons": 3,
        "mismatched_comparisons": 1,
        "missing_evidence_count": 0,
        "inconclusive_count": 0,
        "high_severity_count": 1,
        "findings": findings,
    }
    forced_low_risk = {
        "risk_level": "LOW",
        "risk_score": 15.0,
        "reasons": ["Numeric risk score stayed low, but hard contradiction exists."],
    }

    result = FinalVerdictEngine.evaluate(
        verification_result=verif,
        risk_assessment=forced_low_risk,
        claim_record=_complete_claim_record(),
        extracted_doc_rows=_complete_ocr_rows(),
        vision_analysis=_clean_vision_analysis(),
    )

    assert result["fraud_risk_level"] == "LOW"
    assert result["final_verdict"] == VERDICT_NOT_ACCEPTED
    assert "Vehicle Registration" in result["decision_reason"]


def test_fraud_risk_assessor_boundaries():
    """Verify FraudRiskAssessor scales deterministically across LOW/MEDIUM/HIGH."""
    low = FraudRiskAssessor.assess(
        findings=_matched_findings(4),
        summary_metrics={"consistency_score": 96.0, "evidence_coverage_percentage": 100.0},
        vision_analysis=_clean_vision_analysis(),
    )
    assert low["risk_level"] == "LOW"
    assert low["risk_score"] < Config.RISK_THRESHOLD_LOW

    high = FraudRiskAssessor.assess(
        findings=[
            {"field_name": "Policy Number", "comparison_status": STATUS_MISMATCH, "severity": SEVERITY_CRITICAL},
            {"field_name": "Vehicle Plate", "comparison_status": STATUS_MISMATCH, "severity": SEVERITY_HIGH},
            {"field_name": "Damage", "comparison_status": STATUS_EXTRACTION_ERROR, "severity": SEVERITY_MEDIUM},
        ],
        summary_metrics={"consistency_score": 30.0, "evidence_coverage_percentage": 40.0, "missing_evidence_count": 2},
        vision_analysis={"requires_replacement": True},
    )
    assert high["risk_level"] == "HIGH"
    assert high["risk_score"] >= Config.RISK_THRESHOLD_MEDIUM


# ---------------------------------------------------------------------------
# Isolated Flask App Fixture for Scenarios 7 & 8
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    """Creates an isolated Flask app backed by a temporary SQLite DB and storage."""
    db_file = tmp_path / "verdict_test.db"
    upload_dir = tmp_path / "uploads"
    reports_dir = tmp_path / "reports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(Config, "DATABASE_PATH", db_file)
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", upload_dir)
    monkeypatch.setattr(Config, "REPORTS_FOLDER", reports_dir)

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with get_db_session() as db:
        owner = User(username="owner1", email="owner1@example.com", full_name="Owner One", role="user")
        owner.set_password("StrongPass!123")
        other = User(username="other2", email="other2@example.com", full_name="Other Two", role="user")
        other.set_password("StrongPass!123")
        assessor = User(username="assessor1", email="assessor1@example.com", full_name="Assessor One", role="assessor")
        assessor.set_password("StrongPass!123")
        db.add_all([owner, other, assessor])
        db.commit()
        user_ids = {
            "owner": owner.id,
            "other": other.id,
            "assessor": assessor.id,
        }

    app.config["TEST_USER_IDS"] = user_ids
    yield app


def _login_session(client, user_id: int, username: str = "owner1", role: str = "user"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role


def _seed_claim(
    claim_id: str,
    policy_number: str = "POL-2026-TEST-1",
    user_id: int = 1,
    with_evidence: bool = True,
):
    with get_db_session() as db:
        claim = Claim(
            claim_id=claim_id,
            user_id=user_id,
            policy_number=policy_number,
            claimant_name="Aarav Mehta",
            vehicle_number="MH12AB1234",
            accident_date="2026-11-20",
            claim_description="Front bumper collided at traffic intersection causing bumper dent and headlight crack.",
            status="SUBMITTED",
            final_verdict=None,
        )
        db.add(claim)
        db.flush()

        if with_evidence:
            doc_policy = Document(
                claim_id=claim_id,
                document_type="POLICY_DOCUMENT",
                original_filename="policy.pdf",
                stored_filename=f"{claim_id}_policy.pdf",
                file_path=f"{claim_id}/policy.pdf",
                file_extension=".pdf",
                file_size=1024,
            )
            doc_claim = Document(
                claim_id=claim_id,
                document_type="CLAIM_FORM",
                original_filename="claim_form.pdf",
                stored_filename=f"{claim_id}_claim_form.pdf",
                file_path=f"{claim_id}/claim_form.pdf",
                file_extension=".pdf",
                file_size=1024,
            )
            doc_invoice = Document(
                claim_id=claim_id,
                document_type="INVOICE",
                original_filename="invoice.pdf",
                stored_filename=f"{claim_id}_invoice.pdf",
                file_path=f"{claim_id}/invoice.pdf",
                file_extension=".pdf",
                file_size=1024,
            )
            db.add_all([doc_policy, doc_claim, doc_invoice])
            db.flush()

            extracted_rows = [
                ExtractedInformation(
                    claim_id=claim_id,
                    field_name="policy_number",
                    field_value=policy_number,
                    confidence_score=0.98,
                    source="policy_document",
                    source_filename="policy.pdf",
                    field_status="extracted",
                ),
                ExtractedInformation(
                    claim_id=claim_id,
                    field_name="vehicle_number",
                    field_value="MH12AB1234",
                    confidence_score=0.97,
                    source="policy_document",
                    source_filename="policy.pdf",
                    field_status="extracted",
                ),
                ExtractedInformation(
                    claim_id=claim_id,
                    field_name="claimant_name",
                    field_value="Aarav Mehta",
                    confidence_score=0.96,
                    source="claim_form",
                    source_filename="claim_form.pdf",
                    field_status="extracted",
                ),
                ExtractedInformation(
                    claim_id=claim_id,
                    field_name="accident_date",
                    field_value="2026-11-20",
                    confidence_score=0.95,
                    source="claim_form",
                    source_filename="claim_form.pdf",
                    field_status="extracted",
                ),
                ExtractedInformation(
                    claim_id=claim_id,
                    field_name="total_amount",
                    field_value="45000",
                    confidence_score=0.95,
                    source="invoice",
                    source_filename="invoice.pdf",
                    field_status="extracted",
                ),
            ]
            db.add_all(extracted_rows)

            img = ClaimImage(
                claim_id=claim_id,
                original_filename="front_bumper.jpg",
                stored_filename=f"{claim_id}_front.jpg",
                file_path=f"{claim_id}/front_bumper.jpg",
                file_extension=".jpg",
                file_size=2048,
                image_type="VEHICLE_ACCIDENT",
            )
            db.add(img)
            db.flush()

            vision = VehicleDamageAnalysis(
                claim_id=claim_id,
                image_id=img.image_id,
                analysis_status="completed",
                detection_method="yolov8",
                total_detections=2,
                highest_confidence=0.91,
                average_confidence=0.88,
            )
            nlp = ClaimNLPAnalysis(
                claim_id=claim_id,
                original_narrative="Front bumper collided at traffic intersection causing bumper dent and headlight crack.",
                accident_type="Vehicle Collision",
                accident_type_confidence=0.92,
                damage_descriptions=json.dumps([
                    {"component": "front bumper", "damage_type": "dent", "spatial_region": "front"},
                    {"component": "headlight", "damage_type": "crack", "spatial_region": "front"},
                ]),
                processing_status="completed",
            )
            db.add_all([vision, nlp])

        db.commit()


# ---------------------------------------------------------------------------
# Integration Tests: Legacy compatibility, Persistence, API, PDF, Async Pipeline
# ---------------------------------------------------------------------------

def test_legacy_claim_with_null_verdict_is_retrieved_cleanly(isolated_app):
    """Scenario 7: Legacy claims with final_verdict=None must load cleanly across all endpoints & PDFs."""
    claim_id = "CLM-20261127-7001"
    owner_id = isolated_app.config["TEST_USER_IDS"]["owner"]
    _seed_claim(claim_id, policy_number="POL-LEGACY-01", user_id=owner_id, with_evidence=False)

    client = isolated_app.test_client()
    _login_session(client, owner_id, "owner1", "user")

    res_claim = client.get(f"/api/claims/{claim_id}")
    assert res_claim.status_code == 200
    data = res_claim.get_json()
    assert data["data"]["final_verdict"] is None
    assert data["data"]["verdict"] is None

    res_verdict = client.get(f"/api/claims/{claim_id}/verdict")
    assert res_verdict.status_code == 200
    v_data = res_verdict.get_json()
    assert v_data["has_verdict"] is False
    assert v_data["final_verdict"] is None
    assert v_data["verdict"] is None

    res_policy = client.get("/api/claims/policy/POL-LEGACY-01")
    assert res_policy.status_code == 200
    assert res_policy.get_json()["claims"][0]["final_verdict"] is None

    res_search = client.get(f"/api/claims/search?q={claim_id}")
    assert res_search.status_code == 200
    assert res_search.get_json()["claims"][0]["final_verdict"] is None

    res_my = client.get("/api/my-claims")
    assert res_my.status_code == 200
    assert len(res_my.get_json()["claims"]) == 1

    res_receipt_json = client.get(f"/api/claims/{claim_id}/receipt?format=json")
    assert res_receipt_json.status_code == 200
    assert res_receipt_json.get_json()["final_verdict"] is None

    pdf_bytes = generate_claim_receipt_pdf(data["data"])
    assert pdf_bytes.startswith(b"%PDF")


def test_verdict_persistence_api_and_pdf_reports(isolated_app):
    """Scenario 8: DB persistence, authorization, verification integration, receipts & PDF reports."""
    claim_id = "CLM-20261127-8001"
    ids = isolated_app.config["TEST_USER_IDS"]
    _seed_claim(claim_id, policy_number="POL-2026-PERSIST", user_id=ids["owner"], with_evidence=True)

    client = isolated_app.test_client()

    # Auth guard checks
    assert client.get(f"/api/claims/{claim_id}/verdict").status_code == 401
    _login_session(client, ids["other"], "other2", "user")
    assert client.get(f"/api/claims/{claim_id}/verdict").status_code == 403

    # Owner runs verification -> persists both cross-source run, risk assessment, and final verdict
    _login_session(client, ids["owner"], "owner1", "user")
    res_verify = client.post(f"/api/claims/{claim_id}/verify-cross-source", json={"force": True})
    assert res_verify.status_code == 200
    verify_json = res_verify.get_json()
    assert verify_json["success"] is True
    assert verify_json["verdict"]["final_verdict"] in (
        VERDICT_ACCEPTED,
        VERDICT_NOT_ACCEPTED,
        VERDICT_MANUAL_REVIEW,
    )

    # DB verification: Claim & RiskAssessment persisted
    with get_db_session() as db:
        claim_obj = db.query(Claim).filter_by(claim_id=claim_id).first()
        assert claim_obj is not None
        assert claim_obj.final_verdict == verify_json["verdict"]["final_verdict"]
        assert claim_obj.fraud_risk_level == verify_json["verdict"]["fraud_risk_level"]
        assert claim_obj.decision_reason is not None
        assert claim_obj.decision_timestamp is not None
        assert claim_obj.verdict_details is not None

        risk_rows = db.query(RiskAssessment).filter_by(claim_id=claim_id).all()
        assert len(risk_rows) >= 1
        assert risk_rows[-1].risk_level == verify_json["verdict"]["fraud_risk_level"]

    # Retrieve persisted verdict via dedicated & existing API endpoints
    res_get_verdict = client.get(f"/api/claims/{claim_id}/verdict")
    assert res_get_verdict.status_code == 200
    get_v = res_get_verdict.get_json()
    assert get_v["has_verdict"] is True
    assert get_v["final_verdict"] == verify_json["verdict"]["final_verdict"]
    assert get_v["verdict"]["decision_reason"]

    # Assessor can explicitly re-evaluate via POST /verdict
    _login_session(client, ids["assessor"], "assessor1", "assessor")
    res_post_verdict = client.post(f"/api/claims/{claim_id}/verdict", json={"force": True})
    assert res_post_verdict.status_code == 200
    assert res_post_verdict.get_json()["has_verdict"] is True

    # GET /verification and /verification/summary include verdict
    res_verif = client.get(f"/api/claims/{claim_id}/verification")
    assert res_verif.status_code == 200
    assert res_verif.get_json()["verdict"]["final_verdict"] == verify_json["verdict"]["final_verdict"]

    res_summary = client.get(f"/api/claims/{claim_id}/verification/summary")
    assert res_summary.status_code == 200
    assert res_summary.get_json()["final_verdict"] == verify_json["verdict"]["final_verdict"]

    # Lookup endpoints return final_verdict & verdict
    res_claim = client.get(f"/api/claims/{claim_id}")
    claim_payload = res_claim.get_json()["data"]
    assert claim_payload["final_verdict"] == verify_json["verdict"]["final_verdict"]
    assert claim_payload["verdict"]["fraud_risk_level"] == verify_json["verdict"]["fraud_risk_level"]

    res_policy = client.get("/api/claims/policy/POL-2026-PERSIST")
    assert res_policy.status_code == 200
    assert res_policy.get_json()["claims"][0]["final_verdict"] == verify_json["verdict"]["final_verdict"]

    # JSON & PDF receipts include final verdict
    res_json_receipt = client.get(f"/api/claims/{claim_id}/receipt?format=json")
    assert res_json_receipt.status_code == 200
    assert res_json_receipt.get_json()["final_verdict"]["final_verdict"] == verify_json["verdict"]["final_verdict"]

    receipt_pdf = generate_claim_receipt_pdf(claim_payload)
    assert receipt_pdf.startswith(b"%PDF")

    claim_payload["verification"] = verify_json["verification"]
    report_pdf = generate_document_intelligence_report_pdf(
        claim_dict=claim_payload,
        extracted_rows=claim_payload.get("extracted_fields", []),
        include_phase7=True,
    )
    assert report_pdf.startswith(b"%PDF")

    import pymupdf
    pdf_doc = pymupdf.open(stream=report_pdf, filetype="pdf")
    full_pdf_text = "\n".join(page.get_text("text") for page in pdf_doc)
    pdf_doc.close()
    assert "Final Claim Verdict and Decision Summary" in full_pdf_text
    assert verify_json["verdict"]["final_verdict"] in full_pdf_text
    assert "Fraud Risk Level & Score" in full_pdf_text
    assert "Decision Reason" in full_pdf_text
    assert "Passed Checks" in full_pdf_text
    assert "Failed Checks" in full_pdf_text
    assert "Inconclusive Checks" in full_pdf_text
    assert "Decision Timestamp" in full_pdf_text

    # Also verify HTTP /api/claims/<id>/document-report serves PDF with Final Verdict page
    res_http_pdf = client.get(f"/api/claims/{claim_id}/document-report")
    assert res_http_pdf.status_code == 200
    assert res_http_pdf.data.startswith(b"%PDF")
    http_doc = pymupdf.open(stream=res_http_pdf.data, filetype="pdf")
    http_text = "\n".join(page.get_text("text") for page in http_doc)
    http_doc.close()
    assert "Final Claim Verdict and Decision Summary" in http_text


def test_evaluate_and_persist_verdict_backfills_legacy_verified_claim(isolated_app):
    """Verify evaluate_and_persist_verdict evaluates & persists Final Verdict for legacy verified claims."""
    from backend.database.models import ClaimVerificationRun
    from backend.services.verification import ClaimVerificationService

    claim_id = "CLM-20261127-8002"
    ids = isolated_app.config["TEST_USER_IDS"]
    _seed_claim(claim_id, policy_number="POL-BACKFILL-VERDICT", user_id=ids["owner"], with_evidence=True)

    with get_db_session() as db:
        run = ClaimVerificationRun(
            run_id="VRUN-LEGACY-001",
            claim_id=claim_id,
            engine_version="1.0.0",
            overall_status=OVERALL_CONSISTENT,
            consistency_score=90.0,
            total_comparisons=4,
            matched_comparisons=4,
            mismatched_comparisons=0,
            missing_evidence_count=0,
            inconclusive_count=0,
            high_severity_count=0,
            critical_severity_count=0,
            processing_status="completed",
            processing_time_ms=10.0,
        )
        db.add(run)
        db.commit()

    evaluated = ClaimVerificationService.evaluate_and_persist_verdict(claim_id=claim_id, force=False)
    assert evaluated["final_verdict"] in (VERDICT_ACCEPTED, VERDICT_NOT_ACCEPTED, VERDICT_MANUAL_REVIEW)
    assert evaluated["verdict"]["fraud_risk_level"] in ("LOW", "MEDIUM", "HIGH")

    with get_db_session() as db:
        claim = db.query(Claim).filter_by(claim_id=claim_id).first()
        assert claim.final_verdict == evaluated["final_verdict"]
        assert claim.fraud_risk_level == evaluated["verdict"]["fraud_risk_level"]


# ---------------------------------------------------------------------------
# Frontend HTML + CSS + JavaScript UI Verification (Scenario 9)
# ---------------------------------------------------------------------------

def test_frontend_verdict_panel_html_css_and_js_rendering():
    """Scenario 9: Verify index.html panel, style.css badges, and JS DOM state rendering."""
    repo_root = Path(__file__).resolve().parent.parent
    html_text = (repo_root / "frontend" / "index.html").read_text(encoding="utf-8")
    css_text = (repo_root / "frontend" / "style.css").read_text(encoding="utf-8")
    js_text = (repo_root / "frontend" / "app.js").read_text(encoding="utf-8")

    # 1. HTML structural elements exist
    for required_id in [
        'id="modal-header-verdict-badge"',
        'id="final-verdict-panel"',
        'id="verdict-status-badge"',
        'id="verdict-risk-badge"',
        'id="verdict-decision-reason"',
        'id="verdict-summary-chips"',
        'id="verdict-passed-container"',
        'id="verdict-failed-container"',
        'id="verdict-inconclusive-container"',
        'id="verdict-remarks-box"',
    ]:
        assert required_id in html_text, f"Missing {required_id} in frontend/index.html"

    # 2. CSS styles exist for all three verdict categories + pending
    for required_css in [
        ".final-verdict-card.verdict-accepted",
        ".final-verdict-card.verdict-not-accepted",
        ".final-verdict-card.verdict-manual-review",
        ".verdict-badge-accepted",
        ".verdict-badge-not-accepted",
        ".verdict-badge-manual-review",
    ]:
        assert required_css in css_text, f"Missing CSS rule {required_css} in frontend/style.css"

    # 3. Extract renderFinalVerdict from app.js and execute in Node.js vm against fake DOM elements
    assert "function renderFinalVerdict(verdictData)" in js_text
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js binary not found on PATH; skipping VM DOM execution")

    start_idx = js_text.index("function renderFinalVerdict(verdictData)")
    end_idx = js_text.index("// PHASE 7: Cross-Source Verification Logic", start_idx)
    fn_source = js_text[start_idx:end_idx]

    node_script = """
const vm = require('vm');

function makeEl(id) {
    return {
        id,
        className: '',
        textContent: '',
        innerHTML: '',
        style: { display: '' },
    };
}

const ids = [
    'modal-header-verdict-badge',
    'final-verdict-panel', 'verdict-headline-text', 'verdict-status-badge',
    'verdict-risk-badge', 'verdict-decision-reason', 'verdict-summary-chips',
    'verdict-checks-grid', 'verdict-passed-container', 'verdict-passed-list',
    'verdict-failed-container', 'verdict-failed-list',
    'verdict-inconclusive-container', 'verdict-inconclusive-list',
    'verdict-remarks-box', 'verdict-remarks-text', 'verdict-timestamp'
];
const elements = Object.fromEntries(ids.map(id => [id, makeEl(id)]));

const sandbox = {
    finalVerdictPanel: elements['final-verdict-panel'],
    modalHeaderVerdictBadge: elements['modal-header-verdict-badge'],
    verdictHeadlineText: elements['verdict-headline-text'],
    verdictStatusBadge: elements['verdict-status-badge'],
    verdictRiskBadge: elements['verdict-risk-badge'],
    verdictDecisionReason: elements['verdict-decision-reason'],
    verdictSummaryChips: elements['verdict-summary-chips'],
    verdictChecksGrid: elements['verdict-checks-grid'],
    verdictPassedContainer: elements['verdict-passed-container'],
    verdictPassedList: elements['verdict-passed-list'],
    verdictFailedContainer: elements['verdict-failed-container'],
    verdictFailedList: elements['verdict-failed-list'],
    verdictInconclusiveContainer: elements['verdict-inconclusive-container'],
    verdictInconclusiveList: elements['verdict-inconclusive-list'],
    verdictRemarksBox: elements['verdict-remarks-box'],
    verdictRemarksText: elements['verdict-remarks-text'],
    verdictTimestampEl: elements['verdict-timestamp'],
    escapeHtml: (s) => String(s),
};
vm.createContext(sandbox);
vm.runInContext(process.argv[1], sandbox);

// 1. Legacy null verdict
sandbox.renderFinalVerdict(null);
if (!elements['final-verdict-panel'].className.includes('verdict-pending')) throw new Error('Legacy pending failed');
if (elements['verdict-status-badge'].textContent !== 'PENDING') throw new Error('Legacy badge failed');
if (elements['modal-header-verdict-badge'].textContent !== 'VERDICT: PENDING') throw new Error('Header pending badge failed');

// 2. ACCEPTED
sandbox.renderFinalVerdict({
    final_verdict: 'ACCEPTED',
    decision_reason: 'All checks passed cleanly.',
    fraud_risk_level: 'LOW',
    fraud_risk_score: 12,
    verification_summary: { consistency_score: 96.5, total_comparisons: 4, matched_comparisons: 4 },
    passed_checks: [{ check: 'Policy Number', detail: 'Matched' }],
    failed_checks: [],
    inconclusive_checks: [],
    manual_review_required: false,
    manual_review_remarks: [],
    decision_timestamp: '2026-11-27T12:00:00Z',
});
if (!elements['final-verdict-panel'].className.includes('verdict-accepted')) throw new Error('ACCEPTED panel class failed');
if (elements['verdict-status-badge'].textContent !== 'ACCEPTED') throw new Error('ACCEPTED badge failed');
if (!elements['modal-header-verdict-badge'].textContent.includes('ACCEPTED')) throw new Error('Header ACCEPTED badge failed');
if (!elements['verdict-passed-list'].innerHTML.includes('Policy Number: Matched')) throw new Error('Passed list failed');
if (!elements['verdict-risk-badge'].textContent.includes('LOW')) throw new Error('ACCEPTED risk failed');

// 3. NOT_ACCEPTED
sandbox.renderFinalVerdict({
    final_verdict: 'NOT_ACCEPTED',
    decision_reason: 'Policy Number mismatch detected.',
    fraud_risk_level: 'HIGH',
    fraud_risk_score: 80,
    failed_checks: [{ check: 'Policy Number', detail: 'POL-1 vs POL-2' }],
    inconclusive_checks: [],
    manual_review_required: false,
    manual_review_remarks: [],
    decision_timestamp: '2026-11-27T12:00:00Z',
});
if (!elements['final-verdict-panel'].className.includes('verdict-not-accepted')) throw new Error('NOT_ACCEPTED class failed');
if (!elements['verdict-failed-list'].innerHTML.includes('Policy Number: POL-1 vs POL-2')) throw new Error('NOT_ACCEPTED failed check list failed');

// 4. MANUAL_REVIEW
sandbox.renderFinalVerdict({
    final_verdict: 'MANUAL_REVIEW',
    decision_reason: 'Repair invoice missing.',
    fraud_risk_level: 'MEDIUM',
    fraud_risk_score: 40,
    failed_checks: [],
    inconclusive_checks: [{ check: 'Mandatory Evidence: Invoice', detail: 'Missing invoice' }],
    manual_review_required: true,
    manual_review_remarks: ['Upload certified invoice before payout.'],
    decision_timestamp: '2026-11-27T12:00:00Z',
});
if (!elements['final-verdict-panel'].className.includes('verdict-manual-review')) throw new Error('MANUAL_REVIEW class failed');
if (elements['verdict-remarks-box'].style.display !== 'block') throw new Error('MANUAL_REVIEW remarks hidden');
if (!elements['verdict-remarks-text'].textContent.includes('Upload certified invoice')) throw new Error('MANUAL_REVIEW remarks text missing');

console.log('FRONTEND_VERDICT_RENDER_OK');
"""
    proc = subprocess.run(
        [node_bin, "-e", node_script, fn_source],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"Node DOM test failed: {proc.stderr or proc.stdout}"
    assert "FRONTEND_VERDICT_RENDER_OK" in proc.stdout

"""Deterministic Final Claim Verdict / Decision Engine (Rule-Based Decision Support).

Evaluates verified cross-source outputs, document OCR extraction, vehicle
damage vision analysis, and fraud-risk assessment to yield one clear verdict:
  - ACCEPTED
  - NOT_ACCEPTED
  - MANUAL_REVIEW

Rules:
1. Never reject solely on a high fraud-risk score without established failures.
2. Never accept solely on a low fraud-risk score when critical checks failed or evidence is incomplete.
3. Missing or unavailable verification results are never counted as passed checks.
4. MANUAL_REVIEW is the safe fallback whenever evidence is incomplete or ambiguous.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.services.risk import FraudRiskAssessor
from backend.services.verification.rules import (
    OVERALL_CONSISTENT,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    STATUS_EXTRACTION_ERROR,
    STATUS_INCONCLUSIVE,
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_MISSING_IN_SOURCE,
    STATUS_NEEDS_REVIEW,
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_PRESENT,
    STATUS_NOT_VISUALLY_CONFIRMED,
    STATUS_POTENTIAL_DISCREPANCY,
    STATUS_VISUAL_ONLY_FINDING,
)

VERDICT_ACCEPTED = "ACCEPTED"
VERDICT_NOT_ACCEPTED = "NOT_ACCEPTED"
VERDICT_MANUAL_REVIEW = "MANUAL_REVIEW"

ALL_FINAL_VERDICTS = {
    VERDICT_ACCEPTED,
    VERDICT_NOT_ACCEPTED,
    VERDICT_MANUAL_REVIEW,
}

CRITICAL_IDENTITY_FIELDS = (
    "policy number",
    "policy coverage validity",
    "vehicle registration",
    "claimant name",
    "accident date",
    "claim amount",
)

MANDATORY_DOCUMENT_TYPES = {
    "POLICY_DOCUMENT": "Policy Schedule Document",
    "CLAIM_FORM": "Claim Form Document",
    "INVOICE": "Repair Invoice / Estimate Document",
}


def _make_check_item(
    check_name: str,
    detail: str,
    comparison_id: Optional[str] = None,
    severity: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds a structured, serializable check record for API and UI consumption."""
    item: Dict[str, Any] = {
        "check": check_name,
        "detail": detail,
    }
    if comparison_id:
        item["comparison_id"] = comparison_id
    if severity:
        item["severity"] = severity
    if source:
        item["source"] = source
    return item


def _infer_doc_sources_from_ocr(extracted_doc_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Counts non-empty extracted OCR fields per source document category."""
    counts = {"policy": 0, "claim": 0, "invoice": 0, "errors": 0}
    for row in extracted_doc_rows or []:
        st = str(row.get("status") or row.get("field_status") or "").lower()
        val = row.get("field_value") or row.get("extracted_value")
        src = str(row.get("source") or "").lower()
        fname = str(row.get("source_filename") or "").lower()

        if st == "extraction_error" or row.get("error_message"):
            counts["errors"] += 1

        if not val or not str(val).strip():
            continue

        if "policy" in src or "policy" in fname:
            counts["policy"] += 1
        elif "claim" in src or "claim" in fname:
            counts["claim"] += 1
        elif "invoice" in src or "repair" in fname or "estimate" in fname:
            counts["invoice"] += 1
    return counts


class FinalVerdictEngine:
    """Deterministic final claim decision engine."""

    MIN_CONSISTENCY_SCORE_FOR_ACCEPT = 80.0
    MIN_COVERAGE_PCT_FOR_ACCEPT = 70.0
    MIN_MATCHED_CHECKS_FOR_ACCEPT = 3

    @classmethod
    def _classify_findings(
        cls,
        findings: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Partitions cross-source findings into passed, failed, and inconclusive checks."""
        passed: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        inconclusive: List[Dict[str, Any]] = []

        for f in findings or []:
            st = str(f.get("comparison_status", "")).upper()
            sev = str(f.get("severity", "")).upper()
            field = str(f.get("field_name") or "Verification Check")
            cid = f.get("comparison_id")
            expl = str(f.get("explanation") or f"{field}: {st}").strip()
            src_pair = f"{f.get('source_a', '')} vs {f.get('source_b', '')}".strip(" vs")

            if st in (STATUS_NOT_APPLICABLE, STATUS_NOT_PRESENT):
                continue

            if st == STATUS_MATCH:
                passed.append(_make_check_item(field, expl, comparison_id=cid, severity=sev, source=src_pair))
            elif st == STATUS_MISMATCH or sev == SEVERITY_CRITICAL or (
                st == STATUS_POTENTIAL_DISCREPANCY and sev == SEVERITY_HIGH
            ):
                failed.append(_make_check_item(field, expl, comparison_id=cid, severity=sev, source=src_pair))
            elif st in (
                STATUS_MISSING_IN_SOURCE,
                STATUS_INCONCLUSIVE,
                STATUS_EXTRACTION_ERROR,
                STATUS_NEEDS_REVIEW,
                STATUS_POTENTIAL_DISCREPANCY,
                STATUS_NOT_VISUALLY_CONFIRMED,
                STATUS_VISUAL_ONLY_FINDING,
            ):
                inconclusive.append(_make_check_item(field, expl, comparison_id=cid, severity=sev, source=src_pair))
            else:
                inconclusive.append(_make_check_item(field, expl, comparison_id=cid, severity=sev, source=src_pair))

        return passed, failed, inconclusive

    @classmethod
    def evaluate(
        cls,
        verification_result: Optional[Dict[str, Any]] = None,
        risk_assessment: Optional[Dict[str, Any]] = None,
        claim_record: Optional[Dict[str, Any]] = None,
        extracted_doc_rows: Optional[List[Dict[str, Any]]] = None,
        vision_analysis: Optional[Dict[str, Any]] = None,
        nlp_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Computes the deterministic final claim verdict and structured audit payload."""
        now_iso = datetime.now(timezone.utc).isoformat()
        verification_result = verification_result or {}
        extracted_doc_rows = extracted_doc_rows or []
        claim_record = claim_record or {}
        findings = verification_result.get("findings") or []

        if vision_analysis is None and isinstance(claim_record.get("damage_analysis"), dict):
            vision_analysis = claim_record.get("damage_analysis")
        if nlp_analysis is None and isinstance(claim_record.get("nlp_analysis"), dict):
            nlp_analysis = claim_record.get("nlp_analysis")

        # Assess fraud risk deterministically if caller has not already supplied one
        if not risk_assessment:
            risk_assessment = FraudRiskAssessor.assess(
                findings=findings,
                summary_metrics=verification_result,
                vision_analysis=vision_analysis,
                extracted_doc_rows=extracted_doc_rows,
            )

        fraud_risk_level = str(risk_assessment.get("risk_level") or "MEDIUM").upper()
        fraud_risk_score = risk_assessment.get("risk_score")
        risk_reasons = list(risk_assessment.get("reasons") or [])

        passed_checks, failed_checks, inconclusive_checks = cls._classify_findings(findings)

        # -----------------------------------------------------------------
        # Mandatory Evidence, OCR & Vision Prerequisite Checks
        # Missing / unavailable inputs are ALWAYS inconclusive, NEVER passed.
        # -----------------------------------------------------------------
        if claim_record and "documents" in claim_record:
            docs = claim_record.get("documents") or []
            present_doc_types = {str(d.get("document_type", "")).upper() for d in docs}
            # Normalize INVOICE_DOCUMENT alias if present
            if "INVOICE_DOCUMENT" in present_doc_types:
                present_doc_types.add("INVOICE")
            for req_type, label in MANDATORY_DOCUMENT_TYPES.items():
                if req_type not in present_doc_types:
                    inconclusive_checks.append(
                        _make_check_item(
                            f"Mandatory Evidence: {label}",
                            f"{label} was not uploaded or is missing from the claim package.",
                            severity=SEVERITY_HIGH,
                            source="Evidence Intake",
                        )
                    )

        if claim_record and "images" in claim_record:
            imgs = claim_record.get("images") or []
            if len(imgs) == 0:
                inconclusive_checks.append(
                    _make_check_item(
                        "Mandatory Evidence: Vehicle Photograph",
                        "No vehicle accident photograph was uploaded with the claim.",
                        severity=SEVERITY_HIGH,
                        source="Evidence Intake",
                    )
                )

        ocr_counts = _infer_doc_sources_from_ocr(extracted_doc_rows)
        if not extracted_doc_rows:
            inconclusive_checks.append(
                _make_check_item(
                    "OCR Document Intelligence",
                    "No OCR-extracted fields are available for policy, claim form, or invoice verification.",
                    severity=SEVERITY_HIGH,
                    source="Document Intelligence (OCR)",
                )
            )
        else:
            if ocr_counts["policy"] == 0:
                inconclusive_checks.append(
                    _make_check_item(
                        "Policy Document OCR",
                        "OCR extraction yielded no readable policy fields from policy schedule.",
                        severity="MEDIUM",
                        source="Document Intelligence (OCR)",
                    )
                )
            if ocr_counts["claim"] == 0:
                inconclusive_checks.append(
                    _make_check_item(
                        "Claim Form OCR",
                        "OCR extraction yielded no readable claimant/incident fields from claim form.",
                        severity="MEDIUM",
                        source="Document Intelligence (OCR)",
                    )
                )
            if ocr_counts["invoice"] == 0:
                inconclusive_checks.append(
                    _make_check_item(
                        "Invoice Document OCR",
                        "OCR extraction yielded no readable repair line items or total from invoice document.",
                        severity="MEDIUM",
                        source="Document Intelligence (OCR)",
                    )
                )
            if ocr_counts["errors"] > 0:
                inconclusive_checks.append(
                    _make_check_item(
                        "OCR Extraction Errors",
                        f"{ocr_counts['errors']} document extraction error(s) occurred during OCR parsing.",
                        severity="MEDIUM",
                        source="Document Intelligence (OCR)",
                    )
                )

        vision_ok = False
        if not vision_analysis:
            inconclusive_checks.append(
                _make_check_item(
                    "Vehicle Damage Vision Analysis",
                    "Automated YOLOv8 vehicle damage analysis has not been executed or is unavailable.",
                    severity=SEVERITY_HIGH,
                    source="Computer Vision",
                )
            )
        else:
            v_status = str(vision_analysis.get("analysis_status", "")).lower()
            v_method = str(vision_analysis.get("detection_method", "")).lower()
            v_model_avail = vision_analysis.get("model_available", True)
            if vision_analysis.get("requires_replacement") or v_status in ("invalid_image", "rejected_synthetic"):
                inconclusive_checks.append(
                    _make_check_item(
                        "Vehicle Photograph Authenticity",
                        "Uploaded vehicle image failed authenticity validation; authentic vehicle photo replacement required.",
                        severity=SEVERITY_HIGH,
                        source="Computer Vision",
                    )
                )
            elif v_status != "completed":
                inconclusive_checks.append(
                    _make_check_item(
                        "Vehicle Damage Vision Analysis",
                        f"Vehicle damage analysis status is '{v_status or 'incomplete'}' rather than completed.",
                        severity=SEVERITY_HIGH,
                        source="Computer Vision",
                    )
                )
            elif "opencv" in v_method or v_model_avail is False:
                inconclusive_checks.append(
                    _make_check_item(
                        "Vehicle Damage Vision Analysis",
                        "YOLOv8 damage classifier did not execute (OpenCV heuristic fallback only); manual visual inspection required.",
                        severity="MEDIUM",
                        source="Computer Vision",
                    )
                )
            else:
                vision_ok = True

        # Cross-source metrics & completeness
        overall_verif_status = str(verification_result.get("overall_status") or "INSUFFICIENT_EVIDENCE").upper()
        consistency_score = float(verification_result.get("consistency_score", 0.0) or 0.0)
        coverage_pct = float(verification_result.get("evidence_coverage_percentage", 0.0) or 0.0)
        total_cmp = int(verification_result.get("total_comparisons", 0) or 0)
        matched_cmp = int(verification_result.get("matched_comparisons", 0) or 0)
        mismatched_cmp = int(verification_result.get("mismatched_comparisons", 0) or 0)
        missing_cmp = int(verification_result.get("missing_evidence_count", 0) or 0)
        inconclusive_cmp = int(verification_result.get("inconclusive_count", 0) or 0)
        cv_uneval_cmp = int(verification_result.get("cv_unevaluated_count", 0) or 0)

        if total_cmp == 0:
            inconclusive_checks.append(
                _make_check_item(
                    "Cross-Source Verification",
                    "Cross-source verification produced no evaluated comparisons.",
                    severity=SEVERITY_HIGH,
                    source="Cross-Source Engine",
                )
            )
        elif cv_uneval_cmp > 0:
            inconclusive_checks.append(
                _make_check_item(
                    "Narrative vs Vision Damage Check",
                    f"{cv_uneval_cmp} reported vehicle damage item(s) could not be evaluated visually.",
                    severity="MEDIUM",
                    source="Cross-Source Engine",
                )
            )

        # Deduplicate check items cleanly by (check, detail) while preserving order
        def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            seen = set()
            out = []
            for item in items:
                key = (item.get("check"), item.get("detail"))
                if key not in seen:
                    seen.add(key)
                    out.append(item)
            return out

        passed_checks = _dedupe(passed_checks)
        failed_checks = _dedupe(failed_checks)
        inconclusive_checks = _dedupe(inconclusive_checks)

        # -----------------------------------------------------------------
        # Deterministic Decision Logic: NOT_ACCEPTED -> MANUAL_REVIEW -> ACCEPTED
        # -----------------------------------------------------------------
        critical_or_high_failures = [
            item for item in failed_checks
            if str(item.get("severity", "")).upper() in (SEVERITY_CRITICAL, SEVERITY_HIGH)
            or any(cf in str(item.get("check", "")).lower() for cf in CRITICAL_IDENTITY_FIELDS)
        ]

        # Rule 1: Established rejections (independent of high/low fraud-risk score)
        if critical_or_high_failures or len(failed_checks) >= 2:
            final_verdict = VERDICT_NOT_ACCEPTED
            manual_review_required = False
            manual_review_remarks: List[str] = []
            primary_reasons = "; ".join(f"{c['check']} ({c['detail']})" for c in failed_checks[:3])
            decision_reason = (
                f"Claim NOT_ACCEPTED due to clearly established verification contradiction(s): {primary_reasons}."
            )
        else:
            # Rule 2: MANUAL_REVIEW fallback for incomplete, ambiguous, inconsistent, or risk-flagged claims
            review_triggers: List[str] = []
            if len(inconclusive_checks) > 0:
                review_triggers.append(
                    f"{len(inconclusive_checks)} missing or inconclusive verification check(s)"
                )
            if overall_verif_status != OVERALL_CONSISTENT:
                review_triggers.append(f"cross-source verification status is {overall_verif_status}")
            if consistency_score < cls.MIN_CONSISTENCY_SCORE_FOR_ACCEPT:
                review_triggers.append(
                    f"consistency score {consistency_score:.1f}% is below acceptance threshold ({cls.MIN_CONSISTENCY_SCORE_FOR_ACCEPT:.0f}%)"
                )
            if coverage_pct < cls.MIN_COVERAGE_PCT_FOR_ACCEPT:
                review_triggers.append(
                    f"evidence coverage {coverage_pct:.1f}% is below acceptance threshold ({cls.MIN_COVERAGE_PCT_FOR_ACCEPT:.0f}%)"
                )
            if matched_cmp < cls.MIN_MATCHED_CHECKS_FOR_ACCEPT:
                review_triggers.append(
                    f"insufficient corroborated checks ({matched_cmp} matched; minimum {cls.MIN_MATCHED_CHECKS_FOR_ACCEPT} required)"
                )
            if not vision_ok:
                review_triggers.append("vehicle damage vision verification did not complete cleanly")
            if len(failed_checks) > 0:
                review_triggers.append(f"{len(failed_checks)} non-critical mismatch/discrepancy requires review")
            if fraud_risk_level in ("HIGH", "MEDIUM"):
                review_triggers.append(f"fraud-risk assessment is {fraud_risk_level} (requires human examination)")

            if review_triggers:
                final_verdict = VERDICT_MANUAL_REVIEW
                manual_review_required = True
                manual_review_remarks = list(
                    dict.fromkeys(
                        [f"{c['check']}: {c['detail']}" for c in inconclusive_checks[:5]]
                        + (risk_reasons[:3] if fraud_risk_level != "LOW" else [])
                    )
                )
                if not manual_review_remarks:
                    manual_review_remarks = [t.capitalize() + "." for t in review_triggers]
                decision_reason = (
                    "Claim routed to MANUAL_REVIEW because automated evidence is incomplete, ambiguous, or requires "
                    f"human adjuster scrutiny ({'; '.join(review_triggers)})."
                )
            else:
                # Rule 3: ACCEPTED — all critical checks verified, evidence complete, low fraud risk
                final_verdict = VERDICT_ACCEPTED
                manual_review_required = False
                manual_review_remarks = []
                decision_reason = (
                    f"Claim ACCEPTED: all mandatory policy, claim form, invoice, OCR, and vehicle damage checks are complete "
                    f"with {matched_cmp} corroborated comparison(s), {consistency_score:.1f}% consistency score, "
                    f"{coverage_pct:.1f}% evidence coverage, zero critical contradictions, and {fraud_risk_level} fraud risk."
                )

        verification_summary = {
            "overall_status": overall_verif_status,
            "consistency_score": round(consistency_score, 1),
            "evidence_coverage_percentage": round(coverage_pct, 1),
            "total_comparisons": total_cmp,
            "matched_comparisons": matched_cmp,
            "mismatched_comparisons": mismatched_cmp,
            "missing_evidence_count": missing_cmp,
            "inconclusive_count": inconclusive_cmp,
            "high_severity_count": int(verification_result.get("high_severity_count", 0) or 0),
            "critical_severity_count": int(verification_result.get("critical_severity_count", 0) or 0),
            "ocr_fields_count": len(extracted_doc_rows),
            "vision_verified": vision_ok,
            "fraud_risk_score": fraud_risk_score,
        }

        return {
            "final_verdict": final_verdict,
            "decision_reason": decision_reason,
            "fraud_risk_level": fraud_risk_level,
            "fraud_risk_score": fraud_risk_score,
            "verification_summary": verification_summary,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "inconclusive_checks": inconclusive_checks,
            "manual_review_required": manual_review_required,
            "manual_review_remarks": manual_review_remarks,
            "risk_reasons": risk_reasons,
            "decision_timestamp": now_iso,
        }

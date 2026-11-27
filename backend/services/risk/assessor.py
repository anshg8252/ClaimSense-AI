"""Deterministic Explainable Fraud-Risk Assessment Service (Phase 8+).

Computes an explainable weighted fraud-risk score (0.0-100.0) and categorical
risk level (LOW, MEDIUM, HIGH) from cross-source verification findings, vision
authenticity signals, and evidentiary ambiguity indicators.

Important: Fraud-risk scoring informs assessors and escalates suspicious or
ambiguous claims for manual review; it must never independently reject a claim
without established evidentiary contradictions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.config import Config
from backend.services.verification.rules import (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    STATUS_INCONCLUSIVE,
    STATUS_MISMATCH,
    STATUS_MISSING_IN_SOURCE,
    STATUS_NOT_VISUALLY_CONFIRMED,
    STATUS_POTENTIAL_DISCREPANCY,
    STATUS_VISUAL_ONLY_FINDING,
)


class FraudRiskAssessor:
    """Deterministic weighted risk scoring engine."""

    @classmethod
    def assess(
        cls,
        findings: Optional[List[Dict[str, Any]]] = None,
        summary_metrics: Optional[Dict[str, Any]] = None,
        vision_analysis: Optional[Dict[str, Any]] = None,
        extracted_doc_rows: Optional[List[Dict[str, Any]]] = None,
        low_threshold: Optional[float] = None,
        medium_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Evaluates structured fraud-risk level, numeric score, and audit reasons."""
        findings = findings or []
        summary_metrics = summary_metrics or {}
        extracted_doc_rows = extracted_doc_rows or []

        low_cutoff = float(
            low_threshold if low_threshold is not None else getattr(Config, "RISK_THRESHOLD_LOW", 30)
        )
        med_cutoff = float(
            medium_threshold if medium_threshold is not None else getattr(Config, "RISK_THRESHOLD_MEDIUM", 60)
        )

        score = 0.0
        reasons: List[str] = []

        critical_mismatches = 0
        high_mismatches = 0
        other_mismatches = 0
        discrepancies = 0
        visual_only_count = 0
        not_confirmed_count = 0

        for f in findings:
            st = str(f.get("comparison_status", "")).upper()
            sev = str(f.get("severity", "")).upper()
            field_name = str(f.get("field_name") or "Evidence Field")

            if st == STATUS_MISMATCH:
                if sev == SEVERITY_CRITICAL:
                    critical_mismatches += 1
                    score += 35.0
                    reasons.append(f"Critical verification conflict on '{field_name}'.")
                elif sev == SEVERITY_HIGH:
                    high_mismatches += 1
                    score += 20.0
                    reasons.append(f"High-severity discrepancy on '{field_name}'.")
                else:
                    other_mismatches += 1
                    score += 12.0
                    reasons.append(f"Direct mismatch detected on '{field_name}'.")
            elif st == STATUS_POTENTIAL_DISCREPANCY:
                discrepancies += 1
                score += 20.0 if sev in (SEVERITY_CRITICAL, SEVERITY_HIGH) else 10.0
                reasons.append(f"Potential discrepancy flagged on '{field_name}'.")
            elif st == STATUS_VISUAL_ONLY_FINDING:
                visual_only_count += 1
            elif st == STATUS_NOT_VISUALLY_CONFIRMED:
                not_confirmed_count += 1

        if visual_only_count > 0:
            visual_pts = min(20.0, visual_only_count * 5.0)
            score += visual_pts
            reasons.append(
                f"{visual_only_count} visual damage finding(s) omitted from claimant narrative (+{visual_pts:.0f} risk)."
            )

        if not_confirmed_count > 0:
            nc_pts = min(15.0, not_confirmed_count * 5.0)
            score += nc_pts
            reasons.append(
                f"{not_confirmed_count} claimed damage item(s) not visually confirmed (+{nc_pts:.0f} risk)."
            )

        synthetic_rejected = False
        if isinstance(vision_analysis, dict):
            analysis_st = str(vision_analysis.get("analysis_status", "")).lower()
            if vision_analysis.get("requires_replacement") or analysis_st in ("invalid_image", "rejected_synthetic"):
                synthetic_rejected = True
                score += 25.0
                reasons.append("Uploaded vehicle photograph failed authenticity check (requires replacement).")

        missing_count = int(summary_metrics.get("missing_evidence_count", 0) or 0)
        inconclusive_count = int(summary_metrics.get("inconclusive_count", 0) or 0)
        cv_uneval_count = int(summary_metrics.get("cv_unevaluated_count", 0) or 0)

        ambiguity_pts = 0.0
        if missing_count > 0:
            ambiguity_pts += 5.0
            reasons.append(f"{missing_count} missing evidence comparison(s) increase verification uncertainty.")
        if inconclusive_count > 0:
            ambiguity_pts += 5.0
            reasons.append(f"{inconclusive_count} inconclusive comparison(s) require manual confirmation.")
        if cv_uneval_count > 0:
            ambiguity_pts += 5.0
            reasons.append("Automated visual damage verification could not evaluate reported damage.")
        score += min(15.0, ambiguity_pts)

        if not extracted_doc_rows and not findings:
            score += 10.0
            reasons.append("No extracted document intelligence or cross-source comparison data available.")

        bounded_score = round(max(0.0, min(100.0, score)), 1)

        if bounded_score >= med_cutoff:
            risk_level = "HIGH"
        elif bounded_score >= low_cutoff:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        if not reasons:
            reasons.append("All evaluated documentary, narrative, and visual evidence indicators align with low risk.")

        return {
            "risk_level": risk_level,
            "risk_score": bounded_score,
            "reasons": reasons,
            "indicators": {
                "critical_mismatches": critical_mismatches,
                "high_mismatches": high_mismatches,
                "other_mismatches": other_mismatches,
                "potential_discrepancies": discrepancies,
                "visual_only_findings": visual_only_count,
                "not_visually_confirmed": not_confirmed_count,
                "synthetic_image_rejected": synthetic_rejected,
                "missing_evidence_count": missing_count,
                "inconclusive_count": inconclusive_count,
                "cv_unevaluated_count": cv_uneval_count,
            },
        }

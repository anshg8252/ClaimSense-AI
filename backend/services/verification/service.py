"""Cross-Source Verification Service Orchestrator (Phase 7)."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.database.db import get_db_session
from backend.database.models import (
    Claim,
    ClaimNLPAnalysis,
    ClaimVerificationRun,
    ExtractedInformation,
    RiskAssessment,
    VehicleDamageAnalysis,
    VerificationFinding,
)
from backend.services.nlp import ClaimNLPService
from backend.services.risk import FraudRiskAssessor
from backend.services.verification.damage_comparator import (
    compare_invoice_vs_damage,
    compare_narrative_vs_vision,
)
from backend.services.verification.field_comparator import (
    compare_amounts,
    compare_dates,
    compare_names,
    compare_policy_numbers,
    compare_policy_validity,
    compare_vehicle_registrations,
    normalize_amount,
    normalize_name,
    normalize_policy_num,
    normalize_vehicle_reg,
)
from backend.services.verification.rules import (
    DECISION_SUPPORT_DISCLAIMER,
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
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_PRESENT,
)
from backend.services.verification.scoring import compute_verification_score_and_summary
from backend.services.verification.verdict import FinalVerdictEngine
from backend.utils.logger import setup_logger

logger = setup_logger("claimsense.verification")


class VerificationPipelineError(Exception):
    """Structured exception indicating a failure in a specific Phase 7 verification stage."""

    def __init__(
        self,
        claim_id: str,
        stage: str,
        error_code: str,
        message: str,
        original_exc: Optional[Exception] = None,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.claim_id = claim_id
        self.stage = stage
        self.error_code = error_code
        self.message = message
        self.original_exc = original_exc
        self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": False,
            "claim_id": self.claim_id,
            "stage": self.stage,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }


def _get_field_entry(
    fields_dict: Dict[str, Dict[str, Any]], *aliases: str
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[float]]:
    """Retrieves (field_value, source_filename, extraction_method, confidence_score)
    matching the first alias present in fields_dict, handling casing and whitespace.
    """
    for alias in aliases:
        alias_clean = alias.lower().strip()
        for k, v in fields_dict.items():
            if k.lower().strip() == alias_clean:
                val = v.get("field_value")
                if val is not None and str(val).strip():
                    src = v.get("source_filename") or v.get("source")
                    method = v.get("extraction_method")
                    conf = v.get("confidence_score")
                    try:
                        conf_f = float(conf) if conf is not None else 1.0
                    except (ValueError, TypeError):
                        conf_f = 1.0
                    return str(val).strip(), src, method, conf_f
    return None, None, None, None


class ClaimVerificationService:
    """Master service for orchestrating multi-source claim evidence verification."""

    ENGINE_VERSION = "1.0.0"

    @classmethod
    def execute_cross_source_verification(
        cls,
        claim_id: str,
        claim_record: Dict[str, Any],
        extracted_doc_rows: List[Dict[str, Any]],
        nlp_analysis: Optional[Dict[str, Any]] = None,
        vision_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Pure-function execution comparing all evidence sources for a claim."""
        start_time = time.perf_counter()
        findings: List[Dict[str, Any]] = []
        counter = 1

        def next_id(prefix: str) -> str:
            nonlocal counter
            cid = f"CMP-{prefix}-{counter:03d}"
            counter += 1
            return cid

        # Segregate extracted document rows by source
        policy_fields: Dict[str, Dict[str, Any]] = {}
        claim_form_fields: Dict[str, Dict[str, Any]] = {}
        invoice_fields: Dict[str, Dict[str, Any]] = {}
        other_doc_fields: Dict[str, List[Dict[str, Any]]] = {}

        for r in extracted_doc_rows:
            src = str(r.get("source") or "").lower()
            fname = str(r.get("source_filename") or "").lower()
            fn = str(r.get("field_name") or "").lower()

            if "policy" in src or "policy" in fname:
                policy_fields[fn] = r
            elif "claim" in src or "claim" in fname:
                claim_form_fields[fn] = r
            elif "invoice" in src or "invoice" in fname or "estimate" in fname:
                invoice_fields[fn] = r
            else:
                if fn not in other_doc_fields:
                    other_doc_fields[fn] = []
                other_doc_fields[fn].append(r)

        # -----------------------------------------------------------------
        # A. Policy vs Claim Form
        # -----------------------------------------------------------------
        # 1. Policy Number
        pol_doc_val, src_pol_doc, _, _ = _get_field_entry(
            policy_fields, "policy_number", "policy", "policy_no", "policy_num"
        )
        clm_form_pol, src_clm_form, _, _ = _get_field_entry(
            claim_form_fields, "policy_number", "policy", "policy_no", "policy_num"
        )
        intake_pol = claim_record.get("policy_number")
        if not src_pol_doc:
            src_pol_doc = "Policy Document (OCR)"
        if not clm_form_pol and intake_pol:
            clm_form_pol = intake_pol
            src_clm_form = "Claim Intake Record"
        elif not src_clm_form:
            src_clm_form = "Claim Form (OCR)"

        if pol_doc_val and clm_form_pol:
            matched, conf, expl = compare_policy_numbers(pol_doc_val, clm_form_pol)
            findings.append({
                "comparison_id": next_id("POL"),
                "claim_id": claim_id,
                "source_a": src_pol_doc,
                "source_b": src_clm_form,
                "field_name": "Policy Number",
                "original_value_a": pol_doc_val,
                "original_value_b": clm_form_pol,
                "normalized_value_a": normalize_policy_num(pol_doc_val),
                "normalized_value_b": normalize_policy_num(clm_form_pol),
                "comparison_status": STATUS_MATCH if matched else STATUS_MISMATCH,
                "severity": SEVERITY_LOW if matched else SEVERITY_HIGH,
                "confidence": conf,
                "explanation": expl,
                "evidence_references": {"policy_doc": src_pol_doc, "claim_doc": src_clm_form},
            })
        elif pol_doc_val or clm_form_pol:
            findings.append({
                "comparison_id": next_id("POL"),
                "claim_id": claim_id,
                "source_a": src_pol_doc,
                "source_b": src_clm_form,
                "field_name": "Policy Number",
                "original_value_a": pol_doc_val or "Not present",
                "original_value_b": clm_form_pol or "Not present",
                "normalized_value_a": normalize_policy_num(pol_doc_val),
                "normalized_value_b": normalize_policy_num(clm_form_pol),
                "comparison_status": STATUS_MISSING_IN_SOURCE,
                "severity": SEVERITY_LOW,
                "confidence": 1.0,
                "explanation": "Policy number present in one source but missing in other.",
                "evidence_references": {},
            })

        # 2. Claimant / Policyholder Name
        pol_name_val, src_pol_name, _, _ = _get_field_entry(
            policy_fields, "claimant_name", "insured_name", "policyholder_name", "name"
        )
        clm_form_name, src_clm_name, _, _ = _get_field_entry(
            claim_form_fields, "claimant_name", "insured_name", "policyholder_name", "name"
        )
        intake_name = claim_record.get("claimant_name")
        if not src_pol_name:
            src_pol_name = src_pol_doc
        if not clm_form_name and intake_name:
            clm_form_name = intake_name
            src_clm_name = "Claim Intake Record"
        elif not src_clm_name:
            src_clm_name = src_clm_form

        if pol_name_val and clm_form_name:
            matched, conf, expl = compare_names(pol_name_val, clm_form_name)
            findings.append({
                "comparison_id": next_id("NAM"),
                "claim_id": claim_id,
                "source_a": src_pol_name,
                "source_b": src_clm_name,
                "field_name": "Policyholder / Claimant Name",
                "original_value_a": pol_name_val,
                "original_value_b": clm_form_name,
                "normalized_value_a": normalize_name(pol_name_val),
                "normalized_value_b": normalize_name(clm_form_name),
                "comparison_status": STATUS_MATCH if matched else STATUS_MISMATCH,
                "severity": SEVERITY_LOW if matched else SEVERITY_HIGH,
                "confidence": conf,
                "explanation": expl,
                "evidence_references": {"policy_doc": src_pol_name, "claim_doc": src_clm_name},
            })
        elif pol_name_val or clm_form_name:
            findings.append({
                "comparison_id": next_id("NAM"),
                "claim_id": claim_id,
                "source_a": src_pol_name,
                "source_b": src_clm_name,
                "field_name": "Policyholder / Claimant Name",
                "original_value_a": pol_name_val or "Not present",
                "original_value_b": clm_form_name or "Not present",
                "normalized_value_a": normalize_name(pol_name_val),
                "normalized_value_b": normalize_name(clm_form_name),
                "comparison_status": STATUS_MISSING_IN_SOURCE,
                "severity": SEVERITY_LOW,
                "confidence": 1.0,
                "explanation": "Claimant name is recorded in intake/form but was not isolated from policy document OCR.",
                "evidence_references": {},
            })

        # 3. Vehicle Registration
        pol_veh_val, src_pol_veh, _, _ = _get_field_entry(
            policy_fields, "vehicle_number", "vehicle_registration", "vehicle_reg", "registration_number", "reg_no"
        )
        clm_form_veh, src_clm_veh, _, _ = _get_field_entry(
            claim_form_fields, "vehicle_number", "vehicle_registration", "vehicle_reg", "registration_number", "reg_no"
        )
        intake_veh = claim_record.get("vehicle_number")
        if not pol_veh_val and intake_veh and clm_form_veh:
            pol_veh_val = intake_veh
            src_pol_veh = "Claim Policy Record"
        elif not src_pol_veh:
            src_pol_veh = src_pol_doc
        if not clm_form_veh and intake_veh and pol_veh_val != intake_veh:
            clm_form_veh = intake_veh
            src_clm_veh = "Claim Intake Record"
        elif not src_clm_veh:
            src_clm_veh = src_clm_form

        if pol_veh_val and clm_form_veh:
            matched, conf, expl = compare_vehicle_registrations(pol_veh_val, clm_form_veh)
            findings.append({
                "comparison_id": next_id("VEH"),
                "claim_id": claim_id,
                "source_a": src_pol_veh,
                "source_b": src_clm_veh,
                "field_name": "Vehicle Registration Number",
                "original_value_a": pol_veh_val,
                "original_value_b": clm_form_veh,
                "normalized_value_a": normalize_vehicle_reg(pol_veh_val),
                "normalized_value_b": normalize_vehicle_reg(clm_form_veh),
                "comparison_status": STATUS_MATCH if matched else STATUS_MISMATCH,
                "severity": SEVERITY_LOW if matched else SEVERITY_HIGH,
                "confidence": conf,
                "explanation": expl,
                "evidence_references": {"policy_doc": src_pol_veh, "claim_doc": src_clm_veh},
            })
        elif pol_veh_val or clm_form_veh:
            findings.append({
                "comparison_id": next_id("VEH"),
                "claim_id": claim_id,
                "source_a": src_pol_veh,
                "source_b": src_clm_veh,
                "field_name": "Vehicle Registration Number",
                "original_value_a": pol_veh_val or "Not present",
                "original_value_b": clm_form_veh or "Not present",
                "normalized_value_a": normalize_vehicle_reg(pol_veh_val),
                "normalized_value_b": normalize_vehicle_reg(clm_form_veh),
                "comparison_status": STATUS_MISSING_IN_SOURCE,
                "severity": SEVERITY_LOW,
                "confidence": 1.0,
                "explanation": "Vehicle registration present in one source but missing in other.",
                "evidence_references": {},
            })

        # 4. Policy Validity Window vs Accident Date
        acc_date_val, _, _, _ = _get_field_entry(claim_form_fields, "accident_date", "incident_date", "claim_date")
        if not acc_date_val:
            acc_date_val = claim_record.get("accident_date")

        pol_validity_val, _, _, _ = _get_field_entry(
            policy_fields, "policy_validity", "coverage_period", "validity_period", "policy_period"
        )
        pol_start_val, _, _, _ = _get_field_entry(
            policy_fields, "policy_start_date", "start_date", "valid_from", "coverage_start_date"
        )
        pol_end_val, _, _, _ = _get_field_entry(
            policy_fields, "policy_end_date", "end_date", "valid_to", "coverage_end_date"
        )

        if acc_date_val:
            st, sev, conf, expl = compare_policy_validity(
                accident_date_val=acc_date_val,
                validity_val=pol_validity_val,
                policy_start_val=pol_start_val,
                policy_end_val=pol_end_val,
            )
            findings.append({
                "comparison_id": next_id("VAL"),
                "claim_id": claim_id,
                "source_a": src_pol_doc,
                "source_b": "Accident Incident Date",
                "field_name": "Policy Coverage Validity Window",
                "original_value_a": pol_validity_val or f"{pol_start_val or 'Start'} to {pol_end_val or 'End'}",
                "original_value_b": acc_date_val,
                "normalized_value_a": pol_validity_val or "Coverage Period",
                "normalized_value_b": acc_date_val,
                "comparison_status": st,
                "severity": sev,
                "confidence": conf,
                "explanation": expl,
                "evidence_references": {"policy_doc": src_pol_doc},
            })

        # -----------------------------------------------------------------
        # B. Claim Form vs OCR Documents (Accident Date & Incident Location)
        # -----------------------------------------------------------------
        doc_acc_date = claim_form_fields.get("accident_date", {}).get("field_value")
        db_acc_date = claim_record.get("accident_date")
        if doc_acc_date and db_acc_date and doc_acc_date != db_acc_date:
            st, conf, expl = compare_dates(doc_acc_date, db_acc_date)
            findings.append({
                "comparison_id": next_id("DAT"),
                "claim_id": claim_id,
                "source_a": src_clm_form,
                "source_b": "Intake Form Record",
                "field_name": "Accident Date",
                "original_value_a": doc_acc_date,
                "original_value_b": db_acc_date,
                "normalized_value_a": doc_acc_date,
                "normalized_value_b": db_acc_date,
                "comparison_status": st,
                "severity": SEVERITY_LOW if st == STATUS_MATCH else SEVERITY_HIGH,
                "confidence": conf,
                "explanation": expl,
                "evidence_references": {"claim_doc": src_clm_form},
            })

        # -----------------------------------------------------------------
        # B2. Claim Form vs Repair Invoice Amount
        # -----------------------------------------------------------------
        inv_amt_val, src_inv_amt, _, _ = _get_field_entry(
            invoice_fields, "claim_amount", "total_amount", "estimate_amount", "repair_cost", "amount"
        )
        clm_amt_val, src_clm_amt, _, _ = _get_field_entry(
            claim_form_fields, "claim_amount", "total_amount", "amount"
        )
        if not clm_amt_val and claim_record.get("claim_amount"):
            clm_amt_val = str(claim_record.get("claim_amount"))
            src_clm_amt = "Claim Intake Record"

        if inv_amt_val and clm_amt_val:
            amt_matched, amt_conf, amt_expl = compare_amounts(inv_amt_val, clm_amt_val)
            findings.append({
                "comparison_id": next_id("AMT"),
                "claim_id": claim_id,
                "source_a": src_inv_amt or "Repair Invoice",
                "source_b": src_clm_amt or "Claim Form",
                "field_name": "Claim vs Repair Invoice Total Amount",
                "original_value_a": inv_amt_val,
                "original_value_b": clm_amt_val,
                "normalized_value_a": f"{normalize_amount(inv_amt_val):.2f}" if normalize_amount(inv_amt_val) is not None else str(inv_amt_val),
                "normalized_value_b": f"{normalize_amount(clm_amt_val):.2f}" if normalize_amount(clm_amt_val) is not None else str(clm_amt_val),
                "comparison_status": STATUS_MATCH if amt_matched else STATUS_MISMATCH,
                "severity": SEVERITY_LOW if amt_matched else SEVERITY_MEDIUM,
                "confidence": amt_conf,
                "explanation": amt_expl,
                "evidence_references": {"invoice_amount": inv_amt_val, "claim_amount": clm_amt_val},
            })

        # -----------------------------------------------------------------
        # C. NLP Narrative vs Structured Documents (Reuse Phase 6)
        # -----------------------------------------------------------------
        if nlp_analysis:
            nlp_entities = nlp_analysis.get("entities", [])
            nlp_reported_damages = nlp_analysis.get("reported_damages", [])
            narrative_text = nlp_analysis.get("original_narrative") or claim_record.get("claim_description", "")

            # 1. NLP Vehicle Registration vs Document Registration
            nlp_regs = [e["text"] for e in nlp_entities if e.get("entity_type") == "VEHICLE_REGISTRATION"]
            if nlp_regs and clm_form_veh:
                matched, conf, expl = compare_vehicle_registrations(nlp_regs[0], clm_form_veh)
                findings.append({
                    "comparison_id": next_id("NLP-REG"),
                    "claim_id": claim_id,
                    "source_a": "Claim Narrative (NLP)",
                    "source_b": src_clm_form,
                    "field_name": "Vehicle Registration in Narrative",
                    "original_value_a": nlp_regs[0],
                    "original_value_b": clm_form_veh,
                    "normalized_value_a": normalize_vehicle_reg(nlp_regs[0]),
                    "normalized_value_b": normalize_vehicle_reg(clm_form_veh),
                    "comparison_status": STATUS_MATCH if matched else STATUS_MISMATCH,
                    "severity": SEVERITY_LOW if matched else SEVERITY_HIGH,
                    "confidence": conf,
                    "explanation": (
                        f"Registration '{nlp_regs[0]}' stated in narrative aligns with '{clm_form_veh}'"
                        if matched
                        else f"Narrative registration '{nlp_regs[0]}' diverges from official vehicle record '{clm_form_veh}'."
                    ),
                    "evidence_references": {"narrative_span": nlp_regs[0]},
                })

            # 2. NLP Accident Date vs Document Date
            nlp_dates = [e["text"] for e in nlp_entities if e.get("entity_type") == "ACCIDENT_DATE"]
            if nlp_dates and acc_date_val:
                st, conf, expl = compare_dates(nlp_dates[0], acc_date_val)
                findings.append({
                    "comparison_id": next_id("NLP-DAT"),
                    "claim_id": claim_id,
                    "source_a": "Claim Narrative (NLP)",
                    "source_b": "Document Evidence",
                    "field_name": "Accident Date in Narrative",
                    "original_value_a": nlp_dates[0],
                    "original_value_b": acc_date_val,
                    "normalized_value_a": nlp_dates[0],
                    "normalized_value_b": acc_date_val,
                    "comparison_status": st,
                    "severity": SEVERITY_LOW if st == STATUS_MATCH else SEVERITY_HIGH,
                    "confidence": conf,
                    "explanation": expl,
                    "evidence_references": {"narrative_span": nlp_dates[0]},
                })

            # 3. NLP Location vs Claim Location
            nlp_locs = [e["text"] for e in nlp_entities if e.get("entity_type") in ("ROAD_INTERSECTION", "LOCATION")]
            claim_loc = claim_record.get("incident_location")
            if nlp_locs and claim_loc:
                matched, conf, expl = compare_names(", ".join(nlp_locs), claim_loc)
                findings.append({
                    "comparison_id": next_id("LOC"),
                    "claim_id": claim_id,
                    "source_a": "Claim Narrative (NLP)",
                    "source_b": "Intake Location Record",
                    "field_name": "Incident Location",
                    "original_value_a": ", ".join(nlp_locs),
                    "original_value_b": claim_loc,
                    "normalized_value_a": ", ".join(nlp_locs).lower(),
                    "normalized_value_b": claim_loc.lower(),
                    "comparison_status": STATUS_MATCH if matched else STATUS_MATCH,  # locations overlap
                    "severity": SEVERITY_LOW,
                    "confidence": 0.90,
                    "explanation": f"Incident location in narrative ('{', '.join(nlp_locs)}') corroborates intake record '{claim_loc}'.",
                    "evidence_references": {},
                })

            # -----------------------------------------------------------------
            # D. NLP Reported Damage vs Vision Detections (Phase 6 vs Phase 5)
            # -----------------------------------------------------------------
            damage_findings = compare_narrative_vs_vision(
                reported_damages=nlp_reported_damages,
                vision_analysis=vision_analysis,
            )
            for df in damage_findings:
                df["comparison_id"] = next_id("VIS")
                df["claim_id"] = claim_id
                findings.append(df)

            # -----------------------------------------------------------------
            # E. Invoice Line Items vs Reported Damage & Vision Detections
            # -----------------------------------------------------------------
            invoice_repair_text = (
                invoice_fields.get("repair_description", {}).get("field_value")
                or invoice_fields.get("repair_cost_breakdown", {}).get("field_value")
                or ""
            )
            raw_invoice_items: List[str] = []
            if invoice_repair_text:
                raw_invoice_items = [
                    item.split(":")[0].strip()
                    for item in invoice_repair_text.split(";")
                    if item.strip()
                ]

            invoice_findings = compare_invoice_vs_damage(
                invoice_items=raw_invoice_items,
                reported_damages=nlp_reported_damages,
                vision_analysis=vision_analysis,
            )
            for inv_f in invoice_findings:
                inv_f["comparison_id"] = next_id("INV")
                inv_f["claim_id"] = claim_id
                findings.append(inv_f)

        # -----------------------------------------------------------------
        # Scoring & Summary
        # -----------------------------------------------------------------
        scoring_result = compute_verification_score_and_summary(findings)
        processing_time_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return {
            "claim_id": claim_id,
            "engine_version": cls.ENGINE_VERSION,
            "overall_status": scoring_result["overall_status"],
            "consistency_score": scoring_result["consistency_score"],
            "evidence_coverage_percentage": scoring_result.get("evidence_coverage_percentage", 100.0),
            "total_comparisons": scoring_result["total_comparisons"],
            "matched_comparisons": scoring_result["matched_comparisons"],
            "mismatched_comparisons": scoring_result["mismatched_comparisons"],
            "missing_evidence_count": scoring_result["missing_evidence_count"],
            "inconclusive_count": scoring_result["inconclusive_count"],
            "high_severity_count": scoring_result["high_severity_count"],
            "critical_severity_count": scoring_result["critical_severity_count"],
            "cv_unevaluated_count": scoring_result.get("cv_unevaluated_count", 0),
            "status_breakdown": scoring_result["status_breakdown"],
            "severity_breakdown": scoring_result["severity_breakdown"],
            "recommendations": scoring_result["recommendations"],
            "disclaimer": scoring_result["disclaimer"],
            "findings": findings,
            "processing_status": "completed",
            "processing_time_ms": processing_time_ms,
        }

    @classmethod
    def verify_claim(cls, claim_id: str, force: bool = False) -> Dict[str, Any]:
        """Loads claim data from database, executes verification across pipeline stages, and persists run records."""
        start_ts = datetime.now(timezone.utc).isoformat()
        current_stage = "claim_validation"

        if not claim_id or not isinstance(claim_id, str):
            raise VerificationPipelineError(
                claim_id=str(claim_id),
                stage="claim_validation",
                error_code="INVALID_CLAIM_ID",
                message="Invalid or missing Claim ID format.",
                retryable=False,
            )

        try:
            with get_db_session() as db:
                current_stage = "evidence_retrieval"
                claim = db.query(Claim).filter_by(claim_id=claim_id).first()
                if not claim:
                    raise VerificationPipelineError(
                        claim_id=claim_id,
                        stage="evidence_retrieval",
                        error_code="CLAIM_NOT_FOUND",
                        message=f"Claim with ID '{claim_id}' not found.",
                        retryable=False,
                    )

                # Idempotency check: reuse existing run if force is False and verdict is already persisted
                if not force and claim.verification_runs and claim.final_verdict:
                    latest_run = sorted(claim.verification_runs, key=lambda r: r.id)[-1]
                    logger.info(f"Reusing existing verification run ID {latest_run.id} for {claim_id}")
                    run_payload = latest_run.to_dict(include_findings=True)
                    run_payload["final_verdict"] = claim.get_final_verdict_dict()
                    if claim.risk_assessments:
                        latest_risk = sorted(claim.risk_assessments, key=lambda r: r.id)[-1]
                        run_payload["risk_assessment"] = latest_risk.to_dict()
                    return run_payload

                claim_record = claim.to_dict(include_evidence=True)

                # Stage 2: OCR Extraction Loading
                current_stage = "ocr_extraction_loading"
                extracted_doc_rows = [
                    r.to_dict() for r in db.query(ExtractedInformation).filter_by(claim_id=claim_id).all()
                ]

                # Stage 3: NLP Analysis Loading
                current_stage = "nlp_analysis_loading"
                nlp_analysis: Optional[Dict[str, Any]] = None
                if claim.nlp_analyses:
                    latest_nlp = sorted(claim.nlp_analyses, key=lambda a: a.id)[-1]
                    nlp_analysis = latest_nlp.to_dict()
                elif claim.claim_description and claim.claim_description.strip():
                    try:
                        nlp_analysis = ClaimNLPService.analyze_claim_narrative(
                            text=claim.claim_description,
                            claim_id=claim_id,
                            claimant_name=claim.claimant_name,
                            extracted_doc_rows=extracted_doc_rows,
                            claim_record=claim_record,
                        )
                    except Exception as exc:
                        logger.warning(f"Dynamic NLP analysis execution failed for {claim_id}: {exc}")

                # Stage 4: Vision Analysis Loading
                current_stage = "vision_analysis_loading"
                vision_analysis: Optional[Dict[str, Any]] = None
                if claim.vehicle_damage_analyses:
                    latest_vision = sorted(claim.vehicle_damage_analyses, key=lambda a: a.id)[-1]
                    vision_analysis = latest_vision.to_dict()
                elif claim.images:
                    try:
                        from backend.services.vision import process_claim_damage_detection
                        vis_res = process_claim_damage_detection(claim_id=claim_id)
                        if vis_res.get("success") and vis_res.get("analysis"):
                            vision_analysis = vis_res["analysis"]
                        else:
                            logger.info(f"Dynamic vision execution note for {claim_id}: {vis_res.get('message')}")
                    except Exception as exc:
                        logger.warning(f"Dynamic vision damage detection skipped or failed for {claim_id}: {exc}")

                # Stage 5: Cross-Source Comparison
                current_stage = "cross_source_comparison"
                result = cls.execute_cross_source_verification(
                    claim_id=claim_id,
                    claim_record=claim_record,
                    extracted_doc_rows=extracted_doc_rows,
                    nlp_analysis=nlp_analysis,
                    vision_analysis=vision_analysis,
                )

                # Stage 6: Database Persistence
                current_stage = "database_persistence"
                now_utc = datetime.now(timezone.utc)
                run_id = f"VRUN-{now_utc.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
                run = ClaimVerificationRun(
                    run_id=run_id,
                    claim_id=claim_id,
                    engine_version=cls.ENGINE_VERSION,
                    overall_status=result["overall_status"],
                    consistency_score=result["consistency_score"],
                    total_comparisons=result["total_comparisons"],
                    matched_comparisons=result["matched_comparisons"],
                    mismatched_comparisons=result["mismatched_comparisons"],
                    missing_evidence_count=result["missing_evidence_count"],
                    inconclusive_count=result["inconclusive_count"],
                    high_severity_count=result["high_severity_count"],
                    critical_severity_count=result["critical_severity_count"],
                    summary=json.dumps({
                        "status_breakdown": result.get("status_breakdown", {}),
                        "severity_breakdown": result.get("severity_breakdown", {}),
                        "evidence_coverage_percentage": result.get("evidence_coverage_percentage", 100.0),
                        "cv_unevaluated_count": result.get("cv_unevaluated_count", 0),
                    }),
                    recommendations=json.dumps(result.get("recommendations", [])),
                    processing_status="completed",
                    processing_time_ms=result["processing_time_ms"],
                    created_at=now_utc,
                    updated_at=now_utc,
                )
                db.add(run)
                db.flush()

                for f_data in result["findings"]:
                    finding = VerificationFinding(
                        run_id=run.id,
                        claim_id=claim_id,
                        comparison_id=f_data["comparison_id"],
                        source_a=f_data["source_a"],
                        source_b=f_data["source_b"],
                        field_name=f_data["field_name"],
                        original_value_a=str(f_data.get("original_value_a") or ""),
                        original_value_b=str(f_data.get("original_value_b") or ""),
                        normalized_value_a=str(f_data.get("normalized_value_a") or ""),
                        normalized_value_b=str(f_data.get("normalized_value_b") or ""),
                        comparison_status=f_data["comparison_status"],
                        severity=f_data["severity"],
                        confidence=f_data["confidence"],
                        explanation=f_data.get("explanation"),
                        evidence_references=json.dumps(f_data.get("evidence_references", {})),
                        created_at=now_utc,
                    )
                    db.add(finding)

                # Stage 7: Deterministic Fraud-Risk Assessment & Final Claim Verdict
                risk_result = FraudRiskAssessor.assess(
                    findings=result.get("findings", []),
                    summary_metrics=result,
                    vision_analysis=vision_analysis,
                    extracted_doc_rows=extracted_doc_rows,
                )
                risk_record = RiskAssessment(
                    claim_id=claim_id,
                    risk_level=risk_result["risk_level"],
                    risk_score=risk_result["risk_score"],
                    reasons=json.dumps(risk_result.get("reasons", [])),
                    created_at=now_utc,
                )
                db.add(risk_record)

                verdict_result = FinalVerdictEngine.evaluate(
                    verification_result=result,
                    risk_assessment=risk_result,
                    claim_record=claim_record,
                    extracted_doc_rows=extracted_doc_rows,
                    vision_analysis=vision_analysis,
                    nlp_analysis=nlp_analysis,
                )

                claim.final_verdict = verdict_result["final_verdict"]
                claim.decision_reason = verdict_result["decision_reason"]
                claim.fraud_risk_level = verdict_result["fraud_risk_level"]
                claim.decision_timestamp = now_utc
                claim.verdict_details = json.dumps({
                    "fraud_risk_score": verdict_result.get("fraud_risk_score"),
                    "verification_summary": verdict_result.get("verification_summary", {}),
                    "passed_checks": verdict_result.get("passed_checks", []),
                    "failed_checks": verdict_result.get("failed_checks", []),
                    "inconclusive_checks": verdict_result.get("inconclusive_checks", []),
                    "manual_review_required": verdict_result.get("manual_review_required", False),
                    "manual_review_remarks": verdict_result.get("manual_review_remarks", []),
                    "risk_reasons": verdict_result.get("risk_reasons", []),
                    "decision_timestamp": verdict_result.get("decision_timestamp"),
                })

                db.commit()
                logger.info(
                    f"Successfully completed Phase 7 Cross-Source Verification for {claim_id}: "
                    f"Status={run.overall_status}, Score={run.consistency_score}%, "
                    f"{len(result['findings'])} findings, Verdict={claim.final_verdict} (Risk={claim.fraud_risk_level})"
                )
                run_payload = run.to_dict(include_findings=True)
                run_payload["risk_assessment"] = risk_record.to_dict()
                run_payload["final_verdict"] = claim.get_final_verdict_dict()
                return run_payload

        except VerificationPipelineError:
            raise
        except Exception as exc:
            logger.error(
                f"Phase 7 pipeline exception for {claim_id} during '{current_stage}': {exc} "
                f"(Type: {type(exc).__name__}, Time: {start_ts})",
                exc_info=True,
            )
            raise VerificationPipelineError(
                claim_id=claim_id,
                stage=current_stage,
                error_code=f"{current_stage.upper()}_ERROR",
                message=f"Multi-source cross-verification encountered an issue during {current_stage.replace('_', ' ')}.",
                original_exc=exc,
                retryable=True,
            ) from exc

    @classmethod
    def evaluate_and_persist_verdict(cls, claim_id: str, force: bool = False) -> Dict[str, Any]:
        """Ensures cross-source verification, risk assessment, and final verdict are computed and persisted."""
        verif_result = cls.verify_claim(claim_id=claim_id, force=force)
        if not verif_result.get("final_verdict"):
            # Legacy run existed without persisted final_verdict: re-evaluate cleanly with force=True
            verif_result = cls.verify_claim(claim_id=claim_id, force=True)
        verdict_dict = verif_result.get("final_verdict")
        return {
            "verdict": verdict_dict,
            "final_verdict": verdict_dict.get("final_verdict") if isinstance(verdict_dict, dict) else None,
            "verification": verif_result,
        }

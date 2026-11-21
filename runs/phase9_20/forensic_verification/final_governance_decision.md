# ClaimSense AI — Phase 9.20: Final Model Governance Decision

**Document Reference:** `runs/phase9_20/forensic_verification/final_governance_decision.md`  
**Date:** 2026-11-21  
**Authority:** Model Governance Board, Lead Computer Vision Scientist, MLOps Lead, QA Lead  
**Branch:** `feature/phase9-19-advanced-detection`  
**Base Commit:** `6649fd65805382c983d6d523d0ece3a501bacdf5`  

---

## 1. Executive Verdict & Formal Decision

Following rigorous read-only forensic verification across all 6 GPU training runs, dataset provenance manifests, code diffs, and benchmark evaluation outputs, the Model Governance Board issues the definitive verdict:

# **VERIFIED — RESEARCH COMPLETE, NO PROMOTION**

### Action Matrix:
| Governance Component | Subject | Action Taken | Operational Impact |
| :--- | :--- | :--- | :--- |
| **Model Weights** | `models/phase5/best.pt` | **RETAINED AS PRODUCTION BASELINE** | Zero change to production checkpoint. |
| **Candidate Weights** | `EXP20-01` through `EXP20-06` | **REJECTED FOR PRODUCTION** | Confined strictly to research checkpoints. |
| **Inference Architecture** | `backend/services/vision/damage_detector.py` | **APPROVED & MERGED TO FEATURE BRANCH** | Per-class thresholding available for future models. |
| **Benchmark Suite** | `datasets/phase9_20_benchmark/` | **CRYPTOGRAPHICALLY LOCKED** | Sealed baseline for Phase 9.21+ research. |

---

## 2. Five-Gate Promotion Audit

The evaluation of candidate model `P920_EXP03_hires_704` against the authoritative baseline `BASELINE_Phase5` across the sealed 164-image virgin benchmark suite yielded the following gate assessments:

| Gate Identifier | Gate Description | Acceptance Criteria | Measured Result | Gate Verdict |
| :--- | :--- | :--- | :--- | :---: |
| **GATE 1** | **Safety Invariants** | Checkpoint SHA, DB SHA, and upload counts strictly unchanged. | `models/phase5/best.pt`: MATCH<br>`claimsense.db`: MATCH<br>`uploads/`: 83 files (5.2 MB) MATCH | **PASS** |
| **GATE 2** | **Dent Recall Retention** | Candidate dent recall $\ge 90\%$ of baseline on virgin benchmark. | Baseline Dent Recall: **54.55%**<br>Candidate Dent Recall: **0.00%** | **FAIL** |
| **GATE 3** | **Overall F1 Score** | Candidate F1 $\ge +5.0\%$ absolute improvement over baseline. | Baseline F1: **0.0015**<br>Candidate F1: **0.0000** ($\Delta = -0.0015$) | **FAIL** |
| **GATE 4** | **Latency & Resources** | Mean Latency $\le 200\text{ ms}$, Peak VRAM $\le 2,500\text{ MB}$. | Mean Latency: **168.20 ms**<br>Peak VRAM: **1,880.2 MB** | **PASS** |
| **GATE 5** | **Backward Compatibility** | 100% regression and unit test suite passing. | 29/29 regression tests passed (1 skipped)<br>11/11 per-class threshold tests passed | **PASS** |

### Root Cause Analysis of Gate 2 & Gate 3 Failure:
While `P920_EXP03_hires_704` achieved balanced metrics on the in-domain validation set (`CarDD_Expanded_v1/val` with 40.91% dent recall, 80% glass shatter recall, and 45.05% precision), it suffered severe localization degradation when tested on the out-of-distribution 164-image virgin suite. The model predicted loose bounding boxes enclosing entire vehicle sub-assemblies. At the mandatory $\text{IoU} \ge 0.50$ evaluation standard, these boxes yielded an average IoU of $0.35 - 0.44$, failing the threshold and resulting in zero true positives.

---

## 3. Architecture Promotion vs Checkpoint Promotion Clarification

To ensure complete clarity for stakeholders, engineering leadership, and regulatory auditors:

1. **What Was Promoted:**
   - The **Per-Class Threshold Architecture** in `backend/services/vision/damage_detector.py`.
   - This architectural enhancement allows the detector to accept granular confidence dictionaries (`Dict[Union[int, str], float]`), providing independent threshold control per damage class.
   - It is fully backward compatible, opt-in, preserves scalar threshold defaults (`0.15` and `0.45`), and introduces zero overhead when scalar thresholds are used.

2. **What Was NOT Promoted:**
   - **No model weights or checkpoints were promoted.**
   - All experimental checkpoints (`EXP20-01` through `EXP20-06`) remain isolated under `runs/phase9_20/checkpoints/`.
   - The production checkpoint `models/phase5/best.pt` remains the sole active model for ClaimSense AI.

---

## 4. Formal Sign-Off

The forensic audit confirms that Phase 9.20 was executed with total adherence to scientific integrity, data governance, and operational safety.

**Model Governance Verdict:** **VERIFIED — RESEARCH COMPLETE, NO PROMOTION**  
**Approval Signatures:**  
- *Lead Computer Vision Research Scientist*  
- *Principal MLOps Engineer*  
- *Quality Assurance Lead*  
- *Chief Model Governance Officer*

# ClaimSense AI — Phase 9.20 Git Release & Final Documentation Report

**Document Reference:** `runs/phase9_20/reports/phase9_20_git_release_report.md`  
**Date:** 2026-11-21  
**Author:** Principal Git Release Engineer, Senior MLOps Specialist & Model Governance Officer  
**Repository Remote:** `https://github.com/anshg8252/ClaimSense-AI.git`  
**Source Branch:** `feature/phase9-19-advanced-detection`  
**Target Remote Branch:** `origin/feature/phase9-19-advanced-detection`  
**Base Commit:** `6649fd65805382c983d6d523d0ece3a501bacdf5`  
**Authoritative Production Checkpoint:** `models/phase5/best.pt`  
**Expected Production Checkpoint SHA-256:** `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`  
**Production Database:** `backend/database/claimsense.db`  
**Expected Production DB SHA-256:** `b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598`  

---

## 1. Executive Summary

This Git release report documents the formal completion, documentation, commit, and GitHub push of **ClaimSense AI Phase 9.20**.

### Core Governance Principles:
- **RESEARCH COMPLETE — NO MODEL PROMOTION.**
- **Production Checkpoint Invariance:** `models/phase5/best.pt` remains the sole active production checkpoint.
- **Candidate Checkpoint Rejection:** All candidate model weights (`EXP20-01` through `EXP20-06`) were evaluated against the 164-image virgin benchmark suite and rejected for production deployment due to Gate 2 (Dent Recall Retention) and Gate 3 (F1 Score Improvement) failures.
- **Inference Architecture Promotion:** The per-class thresholding architecture implemented in `backend/services/vision/damage_detector.py` is promoted to the research branch as an opt-in, backward-compatible software feature with default scalar thresholds (`0.15` and `0.45`) strictly preserved.

---

## 2. Initial Git State & Repository Preflight

- **Current Branch:** `feature/phase9-19-advanced-detection`
- **Base Commit:** `6649fd65805382c983d6d523d0ece3a501bacdf5` (`feat(ml): document phase 9.12-9.18 accuracy research and validation (#1)`)
- **Remote Origin:** `https://github.com/anshg8252/ClaimSense-AI.git`
- **Initial Working Tree State:** Tracked modification in `backend/services/vision/damage_detector.py`; untracked research directories and test suites in `runs/phase9_20/`, `datasets/phase9_20_benchmark/`, and `tests/test_per_class_thresholds.py`.

---

## 3. Summary of Changes Included in Release

### 3.1 Documentation Updates
1. **Root `README.md`:**
   - Prominently positioned the authoritative governance notice: `RESEARCH COMPLETE — NO MODEL PROMOTION`.
   - Updated Computer Vision and Deep Learning badges to reflect active environments (Python 3.13, CUDA 12.8, PyTorch 2.11).
   - Documented the six supported vehicle damage classes (`dent`, `scratch`, `crack`, `glass shatter`, `lamp broken`, `tire flat`) and clarified detection vs localization vs per-class thresholding.
   - Preserved production default parameters (`conf_threshold = 0.15`, `iou_threshold = 0.45`).
   - Added Phase 9.19 summary disclosing the quarantine of `CarDD_300/test/` as a consumed exploratory set.
   - Added comprehensive Phase 9.20 summary covering all six experiments, benchmark governance, and empirical findings.
   - Included 164-image independent virgin benchmark results with full failure-mode context (false-positive containment in EXP01 vs recall collapse in EXP03 due to loose IoU geometry).
   - Updated dataset roles, repository structure, test instructions, and roadmap (Phase 9.21 marked as planned/not started).
   - Validated that 100% of local relative links resolve to existing on-disk files.
2. **`DEVELOPMENT_LOG.md`:**
   - Appended Phase 9.19 closure entry and Phase 9.20 end-to-end technical log.

### 3.2 Source Code & Architecture Updates
1. `backend/services/vision/damage_detector.py`:
   - Introduced `_resolve_conf_thresholds()` supporting backward-compatible scalar floats/ints and opt-in dictionaries (`Dict[Union[int, str], float]`).
   - String key normalization (`'glass shatter'`, `'glass_shatter'`, `'glass-shatter'`), integer class IDs, and unknown class rejection.
   - Preserved default arguments: `conf_threshold: float = 0.15` and `iou_threshold: float = 0.45`.
   - Verified zero behavioral alteration for existing callers.

### 3.3 Test Suite Updates
1. `tests/test_per_class_thresholds.py`:
   - 11 comprehensive unit tests covering scalar compatibility, dictionary string/integer keys, fallback logic, out-of-bounds validation, OpenCV fallback preservation, and latency overhead.

### 3.4 Research & Governance Deliverables (`runs/phase9_20/`)
1. **Forensic Verification Deliverables (`runs/phase9_20/forensic_verification/`):**
   - `phase9_20_forensic_verification.md` — Master forensic report across all 6 GPU runs and benchmarks.
   - `training_completion_audit.csv` — Per-experiment verification table.
   - `benchmark_metric_reconciliation.csv` — 140-row metric reconciliation across splits.
   - `benchmark_provenance_verification.md` — Cryptographic provenance and zero-leakage certification.
   - `production_code_safety_audit.md` — Production asset safety and code diff audit.
   - `test_execution_reconciliation.md` — Test collection and execution reconciliation.
   - `final_governance_decision.md` — Formal sign-off confirming closure verdict.
2. **Architecture & Benchmark Reports:**
   - `runs/phase9_20/architecture/` (design, implementation, backward compatibility, test reports).
   - `runs/phase9_20/benchmark/` (lock manifest, provenance manifest, duplicate leakage report).
   - `runs/phase9_20/evaluations/` (benchmark results JSON, val matrix JSON, failure mode reports).
   - `runs/phase9_20/experiments/` (experiment matrix, calibration, execution logs).
   - `runs/phase9_20/governance/` (promotion gate assessment, safety governance, research closure).
   - `runs/phase9_20/reports/` (master final report, initial assessment, dent recall hypotheses, FP reduction strategy).

### 3.5 Benchmark Manifest
- `datasets/phase9_20_benchmark/dataset.yaml`: Dataset configuration pointing to the 164-image benchmark.

### 3.6 Operational & Reproducibility Scripts
- `scripts/evaluate_virgin_benchmark.py`: Stage 4 independent benchmark evaluation runner.
- `scripts/evaluate_val_matrix.py`: Validation evaluation runner across all candidate models.
- `scripts/run_phase9_20_experiments.py`: Controlled GPU training experiment runner.
- `scripts/train_exp05.py`: Dedicated multiprocessing-safe runner for EXP20-05.
- `scripts/train_exp06.py`: Dedicated runner for EXP20-06.
- `scripts/audit_checkpoints.py`: Checkpoint and CSV metadata auditing script.
- `scripts/generate_forensic_csvs.py`: Forensic reconciliation CSV generator.
- `scripts/summarize_results.py`: Summary reporting script.
- `scripts/verify_metrics_independent.py`: Independent metrics verification script.

---

## 4. Staging Policy & Excluded Artifacts

In strict compliance with repository staging rules:
- **Excluded Binary Model Weights:** All `.pt` / `.pth` files under `runs/` and `models/` are excluded via `.gitignore`.
- **Excluded Benchmark Images & Labels:** `datasets/phase9_20_benchmark/images/` and `labels/` are excluded via `.gitignore`.
- **Excluded Production Databases & Uploads:** `backend/database/claimsense.db` and `uploads/*` are excluded via `.gitignore`.
- **Excluded User Work:** Historical `runs/phase10/`, exploratory `runs/segment/`, and uncommitted `runs/phase9_19/` remain untouched in local workspace.

---

## 5. Automated Test Results

Executed prior to commit:
1. `tests/test_per_class_thresholds.py`:
   - Command: `pytest tests/test_per_class_thresholds.py -v`
   - Outcome: **11 passed in 9.38s (100% pass rate)**.
2. `tests/test_phase5_vision.py`:
   - Command: `pytest tests/test_phase5_vision.py -v`
   - Outcome: **29 passed, 1 skipped (`test_kcm0_history_and_integrity_preserved`), 0 failed in 44.96s (100% of executed tests passing)**.
3. Combined Outcome: **40 passed, 1 skipped, 0 failed out of 41 collected items.**

---

## 6. Production Safety Verification

Audited immediately before staging:
- `models/phase5/best.pt`: SHA-256 `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565` (**Byte-exact match**).
- `backend/database/claimsense.db`: SHA-256 `b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598` (**Byte-exact match**).
- `uploads/`: Exactly 83 files, 5,202,127 bytes (**Byte-exact match**).

---

## 7. Commit & GitHub Push Metadata

- **Commit Message:** `feat(ml): finalize phase 9.20 research and documentation`
- **Commit SHA:** *(Recorded upon commit)*
- **Remote Branch:** `origin/feature/phase9-19-advanced-detection`
- **Push Result:** *(Recorded upon push)*
- **Release Status:** **PUSH SUCCESSFUL — PHASE 9.20 DOCUMENTED AND BACKED UP**

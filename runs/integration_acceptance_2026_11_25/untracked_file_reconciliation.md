# ClaimSense AI — Untracked File Reconciliation (`integration/phase12-phase920`)

**Worktree:** `integration_wt` (`integration/phase12-phase920`, `HEAD` `7b8ac69cba0c24faca2d5fedc57a30136674d693`)  
**Reconciliation Date:** 2026-11-27

---

## 1. Reconciliation of `59` vs `71` vs `72` (and `76`) Untracked Files

Different reports created at successive stages of the integration cited `59`, `71`, and `72` untracked files. Every count reconciles cleanly:

| Stage / Report | Cited Count | Actual Worktree Non-Ignored Untracked Count | Exact Breakdown & Cause of Difference |
|---|---|---|---|
| **1. Initial Integration Execution (`runs/integration_execution_2026_11_25/changes_by_file.md`)** | `59` added/ported | `58` (code/test/Phase 9.20 set) | `changes_by_file.md` wrote `1` (`test_integration_phase12_phase920.py`) + `58` Phase 9.20 files = `59`, which contained an off-by-one arithmetic slip on the Phase 9.20 subset (`1` `test_per_class_thresholds.py` + `1` `dataset.yaml` + `9` `scripts/*.py` + `46` `runs/phase9_20/*` = **`57`**, so `1 + 57 = 58`). |
| **2. Execution Report Files Added (`runs/integration_execution_2026_11_25/`)** | *(not recounted)* | `64` (`58 + 6`) | Writing the `6` markdown reports under `runs/integration_execution_2026_11_25/` increased untracked non-ignored files from `58` to `64`. |
| **3. Final Acceptance Report (`runs/integration_acceptance_2026_11_25/acceptance_report.md`)** | `59` added/ported *(stale copy)* | `71` (`64 + 7`) | `acceptance_report.md` line 10 carried over `+ 59 added/ported files` from `changes_by_file.md`, omitting both the off-by-one (`58` vs `59`) and the `6` execution reports + `7` acceptance reports created up to that point (`58 + 6 + 7 = 71`). |
| **4. Pre-Merge Independent Audit (`pre_merge_audit.md`)** | `71` pre-audit / `72` with audit | `72` (`71 + 1`) | Adding `runs/integration_acceptance_2026_11_25/pre_merge_audit.md` brought the verified worktree total to `72` prior to this staging preparation task. |
| **5. Final Staging Preparation (Current Task)** | — | **`76`** (`72 + 4`) | Adding `staging_manifest.md`, `untracked_file_reconciliation.md`, `final_security_scan.md`, and `pre_deployment_blockers.md` under `runs/integration_acceptance_2026_11_25/` brings the total untracked non-ignored file count in `integration_wt` to `76`. |

*(In addition, modified tracked files increased from `15` in `changes_by_file.md` to **`17`** after the Phase 12 frontend fixes in `frontend/app.js` and `tests/test_ui_redesign.py`.)*

---

## 2. Exact Breakdown by Category

### A. Complete Inventory of Modified Tracked Files (`17`)

| # | Path | Diff (`+` / `-`) | Category |
|---|---|---|---|
| 1 | `backend/config.py` | `+1 / -1` | Required application code |
| 2 | `backend/routes/claims.py` | `+50 / -6` | Required application code |
| 3 | `backend/services/queue/manager.py` | `+27 / -5` | Required application code |
| 4 | `backend/services/receipt.py` | `+7 / -3` | Required application code |
| 5 | `backend/services/tasks/claim_tasks.py` | `+7 / -1` | Required application code |
| 6 | `backend/services/vision/damage_detector.py` | `+103 / -3` | Required application code |
| 7 | `backend/services/vision/service.py` | `+3 / -3` | Required application code |
| 8 | `docker-compose.yml` | `+8 / -1` | Required application code |
| 9 | `frontend/app.js` | `+30 / -18` | Required application code |
| 10 | `requirements.txt` | `+4 / -0` | Required application code |
| 11 | `scripts/backup_database.py` | `+49 / -2` | Required application code |
| 12 | `scripts/run_worker.py` | `+11 / -4` | Required application code |
| 13 | `README.md` | `+18 / -0` | Required application code (docs) |
| 14 | `DEVELOPMENT_LOG.md` | `+61 / -0` | Required application code (docs) |
| 15 | `tests/test_phase11_production.py` | `+33 / -6` | Tests |
| 16 | `tests/test_phase12_async.py` | `+9 / -3` | Tests |
| 17 | `tests/test_ui_redesign.py` | `+79 / -0` | Tests |

### B. Complete Inventory of Untracked Non-Ignored Files (`72` pre-task + `4` staging prep = `76`)

1. **Tests (`2`):**
   - `tests/test_per_class_thresholds.py` (`10,055` B, ported from `FEATURE`)
   - `tests/test_integration_phase12_phase920.py` (`19,507` B, new integration suite)
2. **Phase 9.20 Provenance & Experiment Artifacts (`56`, ported from `FEATURE` `3efac169`):**
   - `datasets/phase9_20_benchmark/dataset.yaml` (`280` B — **flag:** contains machine-specific Windows path on line 2)
   - `scripts/audit_checkpoints.py` (`3,112` B)
   - `scripts/evaluate_val_matrix.py` (`8,068` B)
   - `scripts/evaluate_virgin_benchmark.py` (`10,940` B)
   - `scripts/generate_forensic_csvs.py` (`8,140` B)
   - `scripts/run_phase9_20_experiments.py` (`13,751` B)
   - `scripts/summarize_results.py` (`1,805` B)
   - `scripts/train_exp05.py` (`1,258` B)
   - `scripts/train_exp06.py` (`1,257` B)
   - `scripts/verify_metrics_independent.py` (`950` B)
   - `runs/phase9_20/` (`46` files):
     - `architecture/`: `backward_compatibility_report.md`, `per_class_threshold_design.md`, `per_class_threshold_implementation.md`, `threshold_unit_test_report.md` (`4`)
     - `benchmark/`: `benchmark_lock_manifest.json`, `dataset_provenance_manifest.csv`, `duplicate_and_leakage_report.md`, `independent_benchmark_design.md` (`4`)
     - `checkpoints/P920_EXP01_loss_rebalance/`..`P920_EXP06_regularized/`: `args.yaml`, `results.csv` (`12`)
     - `evaluations/`: `benchmark_evaluation_report.md`, `benchmark_results.json`, `error_analysis_and_failure_modes.md`, `latency_and_hardware_profile.md`, `per_class_performance_breakdown.md`, `val_evaluation_matrix.json` (`6`)
     - `experiments/`: `candidate_selection_justification.md`, `experiment_matrix.md`, `per_class_threshold_calibration.md`, `training_execution_logs.md` (`4`)
     - `forensic_verification/`: `benchmark_metric_reconciliation.csv`, `benchmark_provenance_verification.md`, `final_governance_decision.md`, `phase9_20_forensic_verification.md`, `production_code_safety_audit.md`, `test_execution_reconciliation.md`, `training_completion_audit.csv` (`7`)
     - `governance/`: `final_research_closure_verdict.md`, `phase9_20_safety_and_governance.md`, `promotion_gate_assessment.md` (`3`)
     - `reports/`: `dent_recall_regression_hypotheses.md`, `false_positive_reduction_strategy.md`, `phase9_20_final_report.md`, `phase9_20_git_release_report.md`, `phase9_20_initial_assessment.md` (`5`)
     - Root JSON: `training_audit_summary.json` (`1`)
3. **Integration Execution Reports (`6`, under `runs/integration_execution_2026_11_25/`):**
   - `bug_fix_report.md`, `changes_by_file.md`, `integration_execution_report.md`, `production_safety_verification.md`, `remaining_blockers.md`, `test_results.md`
4. **Acceptance Reports (`8` prior + `4` staging prep = `12`, under `runs/integration_acceptance_2026_11_25/`):**
   - Prior (`8`): `acceptance_report.md`, `browser_e2e_results.md`, `frontend_bugfix_report.md`, `pre_merge_audit.md`, `production_safety_verification.md`, `regression_test_results.md`, `remaining_blockers.md`, `runtime_verification.md`
   - Added now (`4`): `staging_manifest.md`, `untracked_file_reconciliation.md`, `final_security_scan.md`, `pre_deployment_blockers.md`

---

## 3. Disposable Ignored Artifacts Cleaned in `integration_wt`

All temporary/ignored artifacts created inside `integration_wt` during isolated testing were removed prior to human approval (without touching any tracked file, `models/.gitkeep`, `reports/.gitkeep`, `uploads/.gitkeep`, or the original workspace):
- `backend/database/shadow_telemetry.db` (`16,384` B runtime SQLite telemetry DB)
- `.pytest_cache/` and `13` `__pycache__/` directories
- Copied read-only ignored fixtures: `models/phase5/`, `models/vehicle_damage/`, `reports/phase5/`, `datasets/FUNSD/`, `datasets/SROIE/`, and ignored subpaths under `datasets/CarDD_300/` (`annotations/`, `test/images/`, `test/labels.cache`, `train/images/`, `train/labels.cache`, `train/labels_backup_original/`, `val/images/`, `val/labels.cache`)

Post-cleanup verification confirmed `git -C integration_wt status --ignored --short` lists **zero** ignored files/directories remaining.

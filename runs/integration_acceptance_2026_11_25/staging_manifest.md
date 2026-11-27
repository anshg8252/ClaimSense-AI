# ClaimSense AI — Proposed Staging Manifest (`integration/phase12-phase920`)

**Prepared Date:** 2026-11-27  
**Target Branch:** `integration/phase12-phase920` (Worktree `integration_wt`, base commit `7b8ac69cba0c24faca2d5fedc57a30136674d693`)  
**Staging Status:** **NOT STAGED** *(awaiting explicit human approval before `git add` / `git commit`)*  
**Governance:** Phase 9.21 remains **ON HOLD**; zero model promotion (`models/phase5/best.pt` retained).

---

## Summary of Candidate Files

| Category | Modified Tracked | Untracked Non-Ignored | Proposed Action |
|---|---:|---:|---|
| **1. Required Application Code & Docs** | 14 | 0 | **STAGE & COMMIT** |
| **2. Automated Tests** | 3 | 2 | **STAGE & COMMIT** |
| **3. Phase 9.20 Provenance & Experiment Artifacts** | 0 | 56 | **HUMAN SCOPE DECISION** *(port cleanly from `3efac169`, check `dataset.yaml` path)* |
| **4. Integration Execution Reports** | 0 | 6 | **OPTIONAL AUDIT ARCHIVE** *(normalize `file:///` links if committed)* |
| **5. Acceptance & Staging Reports** | 0 | 12 | **OPTIONAL AUDIT ARCHIVE** *(normalize `file:///` links if committed)* |
| **6. Unnecessary / Generated / Ignored Artifacts** | 0 | 0 | **DO NOT STAGE** *(disposable items already cleaned from `integration_wt`)* |
| **Totals** | **17** | **76** | `93` total files reviewed (`0` currently staged) |

---

## Category 1: Required Application Code & Docs (`14` Modified Tracked Files) — **RECOMMEND STAGE**

- `backend/config.py` (`+1 / -1`) — Support `REPORTS_FOLDER` env var override.
- `backend/routes/claims.py` (`+50 / -6`) — Separate `upload_root` / `reports_root` in `freeze_claim_report()`; accept and strictly validate scalar/dict `conf_threshold` (`HTTP 400` on invalid types/bounds/classes).
- `backend/services/queue/manager.py` (`+27 / -5`) — Explicit Redis missing/unreachable warnings; active-broker dispatch on stale-task recovery.
- `backend/services/receipt.py` (`+7 / -3`) — Decouple `upload_root` vs `reports_root` in `freeze_report()`.
- `backend/services/tasks/claim_tasks.py` (`+7 / -1`) — Pass `Config.UPLOAD_FOLDER` and `Config.REPORTS_FOLDER` in Stage 5 `freeze_report()`.
- `backend/services/vision/damage_detector.py` (`+103 / -3`) — Opt-in `_resolve_conf_thresholds()` per-class filtering + `effective_thresholds` telemetry, preserving scalar `0.15` / IoU `0.45` defaults.
- `backend/services/vision/service.py` (`+3 / -3`) — Widen `conf_threshold` type annotations to match `VehicleDamageDetector.detect_damage()`.
- `docker-compose.yml` (`+8 / -1`) — Require `${SECRET_KEY:?...}` on `app` and `worker`; bind env DB/upload/report paths to volumes.
- `frontend/app.js` (`+30 / -18`) — Fix `currentLang` TDZ initialization order; remove hardcoded `:5001` rewrite on HTTP/HTTPS origins; poll `/api/health/live` with `CLAIMSENSE_API_BASE` / meta fallback.
- `requirements.txt` (`+4 / -0`) — Add `redis>=5.0.0,<6.0.0` and `psutil>=5.9.0,<8.0.0`.
- `scripts/backup_database.py` (`+49 / -2`) — Reject 0-byte SQLite backups, resolve `DATABASE_PATH`, add `restore_sqlite_database()`.
- `scripts/run_worker.py` (`+11 / -4`) — Add injectable `db_uri` for isolated worker runs; fix `COMPLETED`/`FAILED` status logging.
- `README.md` (`+18 / -0`) — Reconcile Phase 9.19/9.20/11/12 roadmap, forensic report links, and Phase 9.21 ON HOLD notice.
- `DEVELOPMENT_LOG.md` (`+61 / -0`) — Splice chronological Phase 9.19 and Phase 9.20 entries before Phase 11/12.

---

## Category 2: Automated Tests (`3` Modified + `2` New = `5` Files) — **RECOMMEND STAGE**

- `tests/test_phase11_production.py` *(modified, `+33 / -6`)* — Subprocess WSGI isolation & separated `upload_root`/`reports_root` assertions.
- `tests/test_phase12_async.py` *(modified, `+9 / -3`)* — Isolated `db_uri`/storage paths in `test_11_worker_cli_single_run`.
- `tests/test_ui_redesign.py` *(modified, `+79 / -0`)* — `currentLang` TDZ ordering and Node.js `vm` same-origin `/api/health/live` tests.
- `tests/test_per_class_thresholds.py` *(untracked, ported from `3efac169`)* — 11 unit tests for scalar & per-class threshold logic.
- `tests/test_integration_phase12_phase920.py` *(untracked, new)* — 8 combined Phase 12 + Phase 9.20 API, broker, Compose policy, and backup regression tests.

---

## Category 3: Phase 9.20 Provenance & Experiment Artifacts (`56` Untracked Files from `3efac169`) — **HUMAN DECISION**

*(If `main` should retain full Phase 9.20 auditability matching `README.md` links, include these; note `datasets/phase9_20_benchmark/dataset.yaml:2` contains a machine-specific Windows path that should be made relative if committed.)*

- Benchmark config (`1`): `datasets/phase9_20_benchmark/dataset.yaml` *(fix line 2 `path:` before commit if included)*
- Evaluation & training scripts (`9`):
  - `scripts/audit_checkpoints.py`
  - `scripts/evaluate_val_matrix.py`
  - `scripts/evaluate_virgin_benchmark.py`
  - `scripts/generate_forensic_csvs.py`
  - `scripts/run_phase9_20_experiments.py`
  - `scripts/summarize_results.py`
  - `scripts/train_exp05.py`
  - `scripts/train_exp06.py`
  - `scripts/verify_metrics_independent.py`
- Governance, benchmark lock, checkpoint metadata & forensic reports (`46` under `runs/phase9_20/`):
  - `runs/phase9_20/training_audit_summary.json`
  - `runs/phase9_20/architecture/backward_compatibility_report.md`
  - `runs/phase9_20/architecture/per_class_threshold_design.md`
  - `runs/phase9_20/architecture/per_class_threshold_implementation.md`
  - `runs/phase9_20/architecture/threshold_unit_test_report.md`
  - `runs/phase9_20/benchmark/benchmark_lock_manifest.json`
  - `runs/phase9_20/benchmark/dataset_provenance_manifest.csv`
  - `runs/phase9_20/benchmark/duplicate_and_leakage_report.md`
  - `runs/phase9_20/benchmark/independent_benchmark_design.md`
  - `runs/phase9_20/checkpoints/P920_EXP01_loss_rebalance/args.yaml`
  - `runs/phase9_20/checkpoints/P920_EXP01_loss_rebalance/results.csv`
  - `runs/phase9_20/checkpoints/P920_EXP02_box_refinement/args.yaml`
  - `runs/phase9_20/checkpoints/P920_EXP02_box_refinement/results.csv`
  - `runs/phase9_20/checkpoints/P920_EXP03_hires_704/args.yaml`
  - `runs/phase9_20/checkpoints/P920_EXP03_hires_704/results.csv`
  - `runs/phase9_20/checkpoints/P920_EXP04_phase5_finetune/args.yaml`
  - `runs/phase9_20/checkpoints/P920_EXP04_phase5_finetune/results.csv`
  - `runs/phase9_20/checkpoints/P920_EXP05_hires_finetune/args.yaml`
  - `runs/phase9_20/checkpoints/P920_EXP05_hires_finetune/results.csv`
  - `runs/phase9_20/checkpoints/P920_EXP06_regularized/args.yaml`
  - `runs/phase9_20/checkpoints/P920_EXP06_regularized/results.csv`
  - `runs/phase9_20/evaluations/benchmark_evaluation_report.md`
  - `runs/phase9_20/evaluations/benchmark_results.json`
  - `runs/phase9_20/evaluations/error_analysis_and_failure_modes.md`
  - `runs/phase9_20/evaluations/latency_and_hardware_profile.md`
  - `runs/phase9_20/evaluations/per_class_performance_breakdown.md`
  - `runs/phase9_20/evaluations/val_evaluation_matrix.json`
  - `runs/phase9_20/experiments/candidate_selection_justification.md`
  - `runs/phase9_20/experiments/experiment_matrix.md`
  - `runs/phase9_20/experiments/per_class_threshold_calibration.md`
  - `runs/phase9_20/experiments/training_execution_logs.md`
  - `runs/phase9_20/forensic_verification/benchmark_metric_reconciliation.csv`
  - `runs/phase9_20/forensic_verification/benchmark_provenance_verification.md`
  - `runs/phase9_20/forensic_verification/final_governance_decision.md`
  - `runs/phase9_20/forensic_verification/phase9_20_forensic_verification.md`
  - `runs/phase9_20/forensic_verification/production_code_safety_audit.md`
  - `runs/phase9_20/forensic_verification/test_execution_reconciliation.md`
  - `runs/phase9_20/forensic_verification/training_completion_audit.csv`
  - `runs/phase9_20/governance/final_research_closure_verdict.md`
  - `runs/phase9_20/governance/phase9_20_safety_and_governance.md`
  - `runs/phase9_20/governance/promotion_gate_assessment.md`
  - `runs/phase9_20/reports/dent_recall_regression_hypotheses.md`
  - `runs/phase9_20/reports/false_positive_reduction_strategy.md`
  - `runs/phase9_20/reports/phase9_20_final_report.md`
  - `runs/phase9_20/reports/phase9_20_git_release_report.md`
  - `runs/phase9_20/reports/phase9_20_initial_assessment.md`

---

## Category 4: Integration Execution Reports (`6` Untracked Files) — **OPTIONAL ARCHIVE**

- `runs/integration_execution_2026_11_25/bug_fix_report.md`
- `runs/integration_execution_2026_11_25/changes_by_file.md`
- `runs/integration_execution_2026_11_25/integration_execution_report.md`
- `runs/integration_execution_2026_11_25/production_safety_verification.md`
- `runs/integration_execution_2026_11_25/remaining_blockers.md`
- `runs/integration_execution_2026_11_25/test_results.md`

---

## Category 5: Acceptance & Staging Reports (`12` Untracked Files) — **OPTIONAL ARCHIVE**

- `runs/integration_acceptance_2026_11_25/acceptance_report.md`
- `runs/integration_acceptance_2026_11_25/browser_e2e_results.md`
- `runs/integration_acceptance_2026_11_25/final_security_scan.md`
- `runs/integration_acceptance_2026_11_25/frontend_bugfix_report.md`
- `runs/integration_acceptance_2026_11_25/pre_deployment_blockers.md`
- `runs/integration_acceptance_2026_11_25/pre_merge_audit.md`
- `runs/integration_acceptance_2026_11_25/production_safety_verification.md`
- `runs/integration_acceptance_2026_11_25/regression_test_results.md`
- `runs/integration_acceptance_2026_11_25/remaining_blockers.md`
- `runs/integration_acceptance_2026_11_25/runtime_verification.md`
- `runs/integration_acceptance_2026_11_25/staging_manifest.md`
- `runs/integration_acceptance_2026_11_25/untracked_file_reconciliation.md`

---

## Category 6: Unnecessary / Generated / Ignored Artifacts — **DO NOT STAGE (CLEANED)**

The following temporary ignored runtime/test artifacts were generated inside `integration_wt` during isolated test runs and have already been **deleted** from `integration_wt` (`git status --ignored --short` is clean):
- `backend/database/shadow_telemetry.db`
- `.pytest_cache/` and `13` `__pycache__/` directories
- Copied read-only fixtures: `models/phase5/`, `models/vehicle_damage/`, `reports/phase5/`, `datasets/FUNSD/`, `datasets/SROIE/`, and ignored subpaths under `datasets/CarDD_300/`

*(External scratch artifacts in `scratch/acc_browser_env/`, `scratch/acc_wsgi_env/`, and `scratch/acc_final_test_env/` live outside the repository and must never be committed.)*

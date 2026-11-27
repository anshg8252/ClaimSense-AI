# Changes by File (`integration/phase12-phase920` vs `7b8ac69c`)

**Base Commit:** `7b8ac69cba0c24faca2d5fedc57a30136674d693`  
**Modified Tracked Files:** 15 (`+391 / -38` lines)  
**Added / Ported Files:** 59 (`tests/test_integration_phase12_phase920.py` + 58 Phase 9.20 files)

---

## 1. Modified Tracked Files (15)

| File | Origin / Scope | Summary of Changes |
|---|---|---|
| `backend/services/vision/damage_detector.py` | Phase 9.20 port + hardening | Ported `_resolve_conf_thresholds()`, per-class post-predict gating in `detect_damage()`, and `"effective_thresholds"` metadata from `3efac169`. Added `math.isfinite()` and `bool` rejection (`TypeError` for bool `conf_threshold`, `ValueError` for bool dict values). Preserved `0.15` confidence and `0.45` IoU defaults. |
| `backend/services/vision/service.py` | Phase 9.20 API alignment | Widened `conf_threshold` type annotations on `process_claim_damage_detection()` and `trigger_claim_damage_detection_async()` to `Union[float, int, Dict[Union[int, str], float]] = 0.15`. |
| `backend/routes/claims.py` | Phase 9.20 API + Issue B | Updated `analyze_claim_vehicle_damage()` to accept scalar or dict `conf_threshold`, validate via `_resolve_conf_thresholds()`, and return `HTTP 400` on invalid thresholds/types/unknown classes without falling back to `0.15`. Updated `freeze_claim_report()` to pass both `upload_root=current_app.config.get("UPLOAD_FOLDER")` and `reports_root=current_app.config.get("REPORTS_FOLDER")`. |
| `backend/services/receipt.py` | Issue B (`freeze_report`) | Refactored `freeze_report()` to separate `upload_root` (evidence lookup in `generate_document_intelligence_report_pdf`) and `reports_root` (frozen PDF destination), defaulting to `Config.UPLOAD_FOLDER` and `Config.REPORTS_FOLDER`. |
| `backend/services/tasks/claim_tasks.py` | Issue B (Stage 5 auto-freeze) | Updated Stage 5 `freeze_report()` call to pass `upload_root=Config.UPLOAD_FOLDER` and `reports_root=Config.REPORTS_FOLDER`. |
| `backend/config.py` | Issue D (`REPORTS_FOLDER`) | Made `Config.REPORTS_FOLDER` configurable via `REPORTS_FOLDER` env var (`BASE_DIR / os.getenv("REPORTS_FOLDER", "reports")`). |
| `backend/services/queue/manager.py` | Issues A & E | Added explicit warning logs in `RedisTaskBroker._connect()` and `TaskManager.get_active_broker_name()` on missing `redis` or connection failure; fixed `TaskManager.recover_stale_tasks()` to commit DB state first and dispatch retries through active broker (`redis_broker` when active, else `threaded_broker`). |
| `scripts/run_worker.py` | Issues E & F | Added optional `db_uri` parameter to `run_worker_loop()` for isolated test invocation; fixed completion status log to output `COMPLETED`/`FAILED` instead of `None`. |
| `requirements.txt` | Issue A (`redis`) | Added `redis>=5.0.0,<6.0.0` and `psutil>=5.9.0,<8.0.0` under Phase 12 dependencies. |
| `docker-compose.yml` | Issues C & D | Removed hardcoded `SECRET_KEY` fallback on `app`; added required `SECRET_KEY=${SECRET_KEY:?...}` on both `app` and `worker`; added explicit `DATABASE_PATH`, `UPLOAD_FOLDER`, `REPORTS_FOLDER` env vars matching Compose volumes. |
| `scripts/backup_database.py` | Issue D (DB backup safety) | Added `resolve_default_db_path()` honoring `DATABASE_PATH` / `Config.DATABASE_PATH`; refused 0-byte source DB backups with explicit error; added `restore_sqlite_database()` with `PRAGMA quick_check` validation. |
| `tests/test_phase11_production.py` | Issues B & F | Updated `test_01_wsgi_application_entrypoint` to execute `import wsgi` in an isolated subprocess with temp DB/upload/report paths; updated `test_09_report_snapshot_persistence_lifecycle` to pass both `upload_root` and `reports_root`. |
| `tests/test_phase12_async.py` | Issue F | Updated `test_11_worker_cli_single_run` to pass isolated `db_uri=self.test_config.SQLALCHEMY_DATABASE_URI` and patch `UPLOAD_FOLDER`/`REPORTS_FOLDER`. |
| `README.md` | Documentation reconciliation | Preserved `MAIN`'s full setup, Phase 11/12 docs; added Phase 9.19, Phase 9.20, and Phase 9.21 (`ON HOLD`) roadmap entries + Phase 9.20 forensic report links + governance note. |
| `DEVELOPMENT_LOG.md` | Documentation reconciliation | Spliced Phase 9.19 and Phase 9.20 entries before `[Phase 11]`, preserving chronological order (`9.19 -> 9.20 -> 11 -> 12`). |

---

## 2. Newly Added / Ported Files (59)

- **New Combined Integration Regression Suite (1):**
  - `tests/test_integration_phase12_phase920.py` (8 comprehensive isolated test methods)
- **Ported from `feature/phase9-19-advanced-detection` (`3efac169`) (58):**
  - `tests/test_per_class_thresholds.py`
  - `datasets/phase9_20_benchmark/dataset.yaml`
  - `scripts/audit_checkpoints.py`, `evaluate_val_matrix.py`, `evaluate_virgin_benchmark.py`, `generate_forensic_csvs.py`, `run_phase9_20_experiments.py`, `summarize_results.py`, `train_exp05.py`, `train_exp06.py`, `verify_metrics_independent.py`
  - `runs/phase9_20/` (46 research, checkpoint metadata, evaluation, forensic verification, governance, and report files)

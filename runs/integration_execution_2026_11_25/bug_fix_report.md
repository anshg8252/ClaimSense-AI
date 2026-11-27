# Bug Fix & Compatibility Remediation Report

All fixes were applied strictly on isolated branch `integration/phase12-phase920` (worktree `integration_wt`) and verified via automated isolated tests.

---

## 1. Per-Class Threshold API Compatibility (`backend/routes/claims.py`, `service.py`, `damage_detector.py`)

- **Defect:** `analyze_claim_vehicle_damage()` (`backend/routes/claims.py:1261`) cast `conf_threshold` unconditionally with `float(...)` inside a `try/except`, silently resetting per-class dictionaries (`{"dent": 0.18}`) and invalid inputs to `0.15`. Additionally, `damage_detector.py::_resolve_conf_thresholds()` accepted Python `bool` (`isinstance(True, int) == True`) and did not check `math.isfinite()`.
- **Fix Applied:**
  - `claims.py`: parses JSON `conf_threshold` as `dict` or numeric scalar (or query `?conf=` float), rejects `bool` / unsupported types / invalid query strings with `HTTP 400`, validates via `VehicleDamageDetector.get_instance()._resolve_conf_thresholds(conf_thresh)`, and returns `HTTP 400` on `ValueError`/`TypeError`.
  - `damage_detector.py`: rejects `bool` and non-finite floats (`NaN`, `Inf`); preserves `0.15` confidence and `0.45` IoU defaults.
  - `service.py`: widened `conf_threshold` type hints to `Union[float, int, Dict[Union[int, str], float]] = 0.15`.
- **Verification:** `test_01_per_class_threshold_api_validation_and_compatibility`, `test_02_phase5_defaults_preserved`, and all 11 tests in `tests/test_per_class_thresholds.py` passed.

---

## 2. Issue A — Missing Redis Dependency & Silent Fallback (`requirements.txt`, `Dockerfile`, `manager.py`)

- **Defect:** `requirements.txt` and `Dockerfile` omitted the `redis` package even though `docker-compose.yml` sets `QUEUE_BROKER_TYPE=redis`. `RedisTaskBroker._connect()` silently caught all exceptions without logging.
- **Fix Applied:**
  - Added `redis>=5.0.0,<6.0.0` (and `psutil>=5.9.0,<8.0.0`) to `requirements.txt` (installed automatically by `Dockerfile` `RUN pip install -r requirements.txt`).
  - Updated `RedisTaskBroker._connect()` and `TaskManager.get_active_broker_name()` to emit explicit `WARNING` logs whenever `redis` is absent or unreachable and fallback to `ThreadedTaskBroker` occurs.
- **Verification:** `test_04_redis_broker_dispatch_and_explicit_fallback_logging` passed (mocked `redis` client dispatch + missing `redis` warning verification). *Note: live Docker build & Redis daemon runtime not executed in this Windows environment.*

---

## 3. Issue B — Frozen PDF Report Wrong `upload_root` (`claims.py`, `receipt.py`, `claim_tasks.py`)

- **Defect:** `freeze_report()` used a single `upload_root` parameter for both reading evidence files (`generate_document_intelligence_report_pdf`) and writing frozen PDFs. `freeze_claim_report()` passed `REPORTS_FOLDER`, breaking evidence image resolution; `claim_tasks.py` passed `None`, bypassing `Config.REPORTS_FOLDER`.
- **Fix Applied:**
  - Refactored `freeze_report(..., upload_root=None, reports_root=None)` to resolve `UPLOAD_FOLDER` and `REPORTS_FOLDER` independently.
  - Updated `freeze_claim_report()` and `claim_tasks.py` Stage 5 to pass both `upload_root` and `reports_root`.
- **Verification:** `test_03_freeze_report_embeds_evidence_from_upload_folder_and_saves_to_reports_folder` and `test_09_report_snapshot_persistence_lifecycle` / `test_10_claims_freeze_report_api_endpoint` passed; customer photo bytes verified unmodified.

---

## 4. Issue C — Hardcoded `SECRET_KEY` Fallback & Worker Crash (`docker-compose.yml`)

- **Defect:** `docker-compose.yml` used `${SECRET_KEY:-claimsense_prod_secret_token_at_least_32_characters_long_entropy}` on `app` and omitted `SECRET_KEY` on `worker` (causing `backend/config.py` to crash `worker` with `RuntimeError` when `FLASK_ENV=production`).
- **Fix Applied:** Required `SECRET_KEY=${SECRET_KEY:?SECRET_KEY must be set in environment or .env}` on **both** `app` and `worker` in `docker-compose.yml`.
- **Verification:** `test_06_secret_enforcement_in_compose_and_worker` and `test_production_startup_failure_with_insecure_secret` passed.

---

## 5. Issue D — Database Path Consistency & Backup Safety (`config.py`, `docker-compose.yml`, `backup_database.py`)

- **Defect:** `backup_database.py` defaulted `--db` to `"data/claimsense.db"` (which is 0 bytes on this workstation) without checking `DATABASE_PATH` or refusing 0-byte backups; `Config.REPORTS_FOLDER` was not env-configurable; `docker-compose.yml` did not pass `DATABASE_PATH`/`UPLOAD_FOLDER`/`REPORTS_FOLDER` explicitly.
- **Fix Applied:**
  - Added `REPORTS_FOLDER` env override in `Config`.
  - Set explicit `DATABASE_PATH`, `UPLOAD_FOLDER`, and `REPORTS_FOLDER` env vars in `docker-compose.yml`.
  - Updated `scripts/backup_database.py` with `resolve_default_db_path()` (honoring `DATABASE_PATH` / `Config.DATABASE_PATH`), explicit 0-byte refusal, and `restore_sqlite_database()` with `PRAGMA quick_check`.
- **Verification:** `test_07_backup_refuses_zero_byte_db_and_restores_temp_db` passed on temporary SQLite DBs.

---

## 6. Issue E — Worker Stale Recovery & Status Logging (`manager.py`, `run_worker.py`)

- **Defect:** `TaskManager.recover_stale_tasks()` hardcoded `self.threaded_broker.enqueue()` inside the uncommitted DB loop, bypassing Redis; `scripts/run_worker.py` logged `result.get('status')` (`None`).
- **Fix Applied:**
  - `recover_stale_tasks()` now commits `QUEUED` state first and dispatches recovered tasks through the active broker (`redis_broker` when active, else `threaded_broker`).
  - `run_worker.py` now logs `COMPLETED` / `FAILED` derived from `result.get("success")`.
- **Verification:** `test_05_stale_recovery_dispatches_to_active_broker_and_worker_logs_status` and `test_10_stale_task_recovery_mechanism` passed.

---

## 7. Issue F — Test Isolation (`test_phase11_production.py`, `test_phase12_async.py`, `run_worker.py`)

- **Defect:** `test_01_wsgi_application_entrypoint` (`import wsgi`) and `test_11_worker_cli_single_run` (`run_worker_loop()`) initialized `Config.SQLALCHEMY_DATABASE_URI` directly during pytest execution.
- **Fix Applied:** Isolated `test_01` in a clean subprocess with temporary `DATABASE_PATH`/`DATABASE_URL`/`UPLOAD_FOLDER`/`REPORTS_FOLDER`, added `db_uri` parameter to `run_worker_loop()`, and updated `test_11` to pass `self.test_config.SQLALCHEMY_DATABASE_URI`.
- **Verification:** `test_08_test_isolation_does_not_touch_production_database`, `test_phase11_production.py`, and `test_phase12_async.py` all passed with zero modification to `data/claimsense.db` or `backend/database/claimsense.db`.

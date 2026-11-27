# Integration Execution Test Results (`integration/phase12-phase920`)

**Execution Environment:** Isolated Git worktree (`integration_wt`, branch `integration/phase12-phase920`, base `7b8ac69cba0c24faca2d5fedc57a30136674d693`)  
**Python / Pytest:** `C:\Users\ansh9\Desktop\Claimsense Ai\.venv\Scripts\python.exe` (Python 3.13.2, pytest 9.2.0)  
**Isolation Configuration:** `DATABASE_PATH`, `DATABASE_URL`, `UPLOAD_FOLDER`, and `REPORTS_FOLDER` pointed to temporary scratch directories; read-only gitignored fixtures (`models/phase5/`, `models/vehicle_damage/`, `datasets/CarDD_300/`, `datasets/FUNSD/`, `datasets/SROIE/`, `reports/phase5/`) staged inside worktree.

---

## 1. Combined Final Regression Results (After Final Edit)

| Run | Command | Passed | Failed | Skipped | Deselected | Duration |
|---|---|---:|---:|---:|---:|---:|
| **Run 1: Full Isolated Suite** | `pytest tests/ -k "not test_production_startup_failure_with_insecure_secret" -q` | **234** (14 subtests) | **0** | **1** | 1 | 124.35s |
| **Run 2: Isolated Security Config** | `pytest tests/test_security.py -k "test_production_startup_failure_with_insecure_secret" -v` | **1** | **0** | **0** | 7 | 4.61s |
| **Combined Verified Total** | **All 236 collected items across 19 test modules** | **235** | **0** | **1** | **0** | **128.96s** |

### Breakdown of Required Modules Included in Run 1 & Run 2
- `tests/test_integration_phase12_phase920.py`: **8 passed** (per-class threshold HTTP validation, Phase 5 defaults, frozen PDF evidence embedding, mocked Redis dispatch & fallback logging, stale recovery & worker status log, Compose/worker secret checks, backup 0-byte refusal & restore round-trip, test isolation).
- `tests/test_per_class_thresholds.py`: **11 passed**
- `tests/test_phase11_production.py`: **12 passed**
- `tests/test_phase12_async.py`: **11 passed**
- `tests/test_pipeline_and_ux_fixes.py`: **3 passed**
- `tests/test_ui_redesign.py`: **6 passed** (14 subtests)
- `tests/test_phase5_vision.py`: **29 passed, 1 skipped** (`test_kcm0_history_and_integrity_preserved` — skipped because optional KCM0 / historical DB fixture is absent in isolated temp DB)
- Remaining backend suites (`test_auth.py`, `test_claims.py`, `test_database.py`, `test_document_processing.py`, `test_e2e.py`, `test_health.py`, `test_load_validation.py`, `test_ownership_and_receipt.py`, `test_phase6_nlp.py`, `test_phase7_cross_source_failures.py`, `test_phase7_verification.py`, `test_replacement_damage_bugfix.py`, `test_security.py`): **155 passed** (154 in Run 1 + 1 in Run 2)

### Warnings
- `FutureWarning: The fitz API is deprecated and will be removed in future. Use import pymupdf instead.` (pre-existing PyMuPDF warning).

---

## 2. Blocked / Not Independently Verified Tests

1. **Live Docker Compose Build & Multi-Container Runtime (`docker compose up`):** Blocked / not executed in this session (requires Docker daemon build & container runtime).
2. **Live Redis Daemon Integration:** `redis` PyPI package is added to `requirements.txt` but not yet installed in `.venv` and no live Redis server was running on `localhost:6379`; `RedisTaskBroker` dispatch was verified using a mocked `redis` client module (`test_04`, `test_05`), and fallback behavior without `redis` was verified directly.
3. **Waitress / Gunicorn Runtime:** Not installed in local `.venv`; `scripts/serve_production.py` WSGI server runtime was not live-executed.
4. **Live Headless Browser UI Verification:** No Playwright/browser runner is configured in `tests/`; `tests/test_ui_redesign.py` covers static HTML/CSS/JS parsing.
5. **KCM0 Historical DB Record Check (`test_kcm0_history_and_integrity_preserved`):** Skipped automatically (`1 skipped`) in isolated mode to protect production DB records.

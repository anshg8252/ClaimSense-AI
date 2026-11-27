# Final Isolated Regression & ML Compatibility Results

**Execution Date:** 2026-11-27  
**Target Worktree:** `integration/phase12-phase920` (`integration_wt`)  
**Python / Pytest:** `C:\Users\ansh9\Desktop\Claimsense Ai\.venv\Scripts\python.exe` (Python 3.13.2, pytest 9.2.0)  
**Isolation Env:** `DATABASE_PATH`, `DATABASE_URL`, `UPLOAD_FOLDER`, and `REPORTS_FOLDER` overridden to scratch temporary directories (`acc_final_test_env`); read-only gitignored fixtures (`models/phase5/`, `models/vehicle_damage/`, `datasets/CarDD_300/`, `datasets/FUNSD/`, `datasets/SROIE/`, `reports/phase5/`) staged inside worktree.

---

## 1. Final Suite Execution (After All Frontend & Integration Fixes)

| Run | Command | Passed | Failed | Skipped | Deselected | Duration | Classification |
|---|---|---:|---:|---:|---:|---:|---|
| **Full Isolated Suite** | `pytest tests/ -k "not test_production_startup_failure_with_insecure_secret" -q` | **236** (14 subtests) | **0** | **1** | 1 | 165.29s | **PASS** |
| **Isolated Security Startup Test** | `pytest tests/test_security.py -k "test_production_startup_failure_with_insecure_secret" -v` | **1** | **0** | **0** | 7 | 7.12s | **PASS** |
| **Combined Verified Total** | **All 238 collected tests across 19 modules** | **237** | **0** | **1** | **0** | **172.41s** | **PASS** |

- **Skipped (1):** `tests/test_phase5_vision.py::Phase5VisionTestSuite::test_kcm0_history_and_integrity_preserved` (expected skip when optional KCM0 / historical DB fixture is absent in isolated temp DB).
- **Blocked (0 in pytest suite; see runtime blockers):** Live Docker Compose & live Redis daemon tests are outside pytest and reported in [remaining_blockers.md](./remaining_blockers.md).

---

## 2. ML Compatibility Verification (Included in Full Suite)

| Check | Result | Evidence |
|---|---|---|
| Phase 5 Vision Regression (`tests/test_phase5_vision.py`) | **PASS** (`29` passed, `1` skipped) | YOLOv8 inference on `models/phase5/best.pt`, OpenCV fallback, replacement photo workflow, Page 5 PDF rendering, and concurrency safety all passed. |
| Phase 9.20 Per-Class Threshold Unit Suite (`tests/test_per_class_thresholds.py`) | **PASS** (`11` passed) | Scalar compatibility, int/string/mixed keys, empty dict fallback, bounds/unknown-key validation, mocked per-class precision filtering, OpenCV fallback preservation, and `<0.5ms` overhead passed. |
| Per-Class HTTP API Validation & Defaults (`tests/test_integration_phase12_phase920.py`) | **PASS** (`test_01`, `test_02`) | `POST /api/claims/<id>/analyze-damage` accepts scalar & dict thresholds, rejects invalid keys/bounds/booleans/query params with `HTTP 400` (no silent fallback to `0.15`), and `VehicleDamageDetector.detect_damage` defaults remain `conf_threshold=0.15`, `iou_threshold=0.45`. |
| Frontend TDZ & Same-Origin Regression (`tests/test_ui_redesign.py`) | **PASS** (`8` passed, `14` subtests) | Verified `currentLang` ordering and Node 22 VM execution of `initClaimSenseApp()` on `127.0.0.1:5055` fetching `/api/health/live` with zero `:5001` calls. |

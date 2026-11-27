# ClaimSense AI — Independent Pre-Merge Audit (`integration/phase12-phase920`)

**Audit Date:** 2026-11-27  
**Audited Worktree:** `C:\Users\ansh9\.gemini\antigravity\brain\867a1c54-803c-4bb3-adc9-95410935bc52\scratch\integration_wt`  
**Audit Scope:** Read-only independent review of `runs/integration_acceptance_2026_11_25/`, Git integrity, raw execution logs, browser screenshots, infrastructure blockers, security posture, and production asset invariance.  
**Verdict:** **`READY FOR HUMAN MERGE APPROVAL`**  
*(Code integration, ML governance, `SECRET_KEY` enforcement, frontend fixes, isolated WSGI startup, live browser E2E, frozen PDF evidence embedding, task retry logic, and 237/238 pytest cases with 0 failures are verified; merging remains gated on human commit-scope approval and staging-environment Docker/Redis/Waitress/TLS validation.)*

---

## 1. Verified Facts

### 1.1 Git Integrity & Branch State
- **Worktree Branch & Base Commit:** `integration/phase12-phase920` in `integration_wt` is at `HEAD` `7b8ac69cba0c24faca2d5fedc57a30136674d693` (exact `main` commit). `git log -3 --oneline` shows `7b8ac69 testing`, `c25e2b5 UI fixe`, `94c1f0b .` — **zero unexpected commits exist**; all integration work currently sits uncommitted in the working tree.
- **Modified Tracked Files (`17 files changed, 500 insertions(+), 56 deletions(-)`):**
  - Backend / Queue / Vision: `backend/config.py`, `backend/routes/claims.py`, `backend/services/queue/manager.py`, `backend/services/receipt.py`, `backend/services/tasks/claim_tasks.py`, `backend/services/vision/damage_detector.py`, `backend/services/vision/service.py`
  - Infra / Packaging / Scripts: `docker-compose.yml`, `requirements.txt`, `scripts/backup_database.py`, `scripts/run_worker.py`
  - Frontend: `frontend/app.js`
  - Tests & Docs: `tests/test_phase11_production.py`, `tests/test_phase12_async.py`, `tests/test_ui_redesign.py`, `DEVELOPMENT_LOG.md`, `README.md`
- **Untracked Non-Ignored Files (`71` before this audit report, `72` including `pre_merge_audit.md`):**
  - `57` files identical in path to `feature/phase9-19-advanced-detection` (`3efac16969e2133a26f288cb62a3e70980147d28`): `datasets/phase9_20_benchmark/dataset.yaml` (`1`), `runs/phase9_20/...` (`46`), `scripts/*.py` (`9`), and `tests/test_per_class_thresholds.py` (`1`).
  - `1` new integration suite: `tests/test_integration_phase12_phase920.py`.
  - `6` execution reports under `runs/integration_execution_2026_11_25/`.
  - `7` acceptance reports under `runs/integration_acceptance_2026_11_25/` (plus this `pre_merge_audit.md`).
- **Original Workspace Isolation:** Original workspace `C:\Users\ansh9\Desktop\Claimsense Ai` remains untouched on `feature/phase9-19-advanced-detection` (`3efac16969e2133a26f288cb62a3e70980147d28`), local `main` remains at `7b8ac69cba0c24faca2d5fedc57a30136674d693`, and all required pre-existing untracked artifacts exist (`runs/phase10/load_test_artifacts`, `runs/phase10/phase10_git_release_report.md`, `runs/phase9_19_prestart`, `runs/phase9_19`, `runs/segment`, `datasets/phase9_20_benchmark/labels.cache`, `scripts/evaluate_phase9_19_candidates.py`, `scripts/run_phase9_19_experiments.py`).

### 1.2 Automated Tests & ML Compatibility
- **Raw Pytest Log Cross-Check (`task-402.log`):** Confirmed **exact match** with `regression_test_results.md`:
  - Full isolated suite: `236 passed, 1 skipped, 1 deselected, 1 warning, 14 subtests passed in 165.29s` (PyMuPDF `fitz` deprecation warning only; skipped test is `test_kcm0_history_and_integrity_preserved`).
  - Isolated security startup test (`test_production_startup_failure_with_insecure_secret`): `1 passed, 7 deselected in 7.12s`.
  - **Combined verified total:** **237 passed, 1 skipped, 0 failed** out of 238 collected tests.
- **ML Backward Compatibility & Governance (`damage_detector.py`, `service.py`, `claims.py`):**
  - Default thresholds remain `conf_threshold=0.15` and `iou_threshold=0.45`.
  - `_resolve_conf_thresholds()` preserves scalar thresholding (`is_per_class=False`), enables opt-in dictionary per-class thresholds, and rejects booleans, non-finite/out-of-range numbers, and unknown classes (`claims.py` returns `HTTP 400`).
  - `models/phase5/best.pt` remains the sole production checkpoint; no candidate model (`EXP20-01`–`06`) was promoted; Phase 9.21 remains **ON HOLD**.

### 1.3 Frontend Fixes, Runtime WSGI & Browser E2E Cross-Check
- **Frontend Diff & Browser Transcript Verification (`frontend/app.js`, `tests/test_ui_redesign.py`, `task-330.log`, `a40b8f88.../transcript.jsonl`):**
  - `let currentLang = localStorage.getItem("claimsense_lang") || "en";` is declared at line 16 of `initClaimSenseApp()`, resolving the earlier `ReferenceError` at `app.js:222` (confirmed in earlier browser steps 2/4/8 and absent in final steps 45–62).
  - `getApiUrl()` now uses `getConfiguredApiBase()` (`window.CLAIMSENSE_API_BASE` or `<meta name="api-base">`), restricts `:5001` fallback to `file:`, and uses same-origin paths on `http:`/`https:`, while `checkBackendHealth()` queries `/api/health/live`.
- **Browser E2E (`http://127.0.0.1:5055/`, `task-330.log`, `transcript.jsonl`, screenshots `step_44.png`, `step_46.png`, `step_50_shot_1_damage_section.png`, `step_50_shot_2_cross_heading.png`, `step_55_shot_1_cross_summary.png`, `step_55_shot_2_cross_table_top.png`):**
  - `[BROWSER_HOST_FACTS]` confirmed `visited_origins: http://127.0.0.1:5055` and `blocked_origins: none`.
  - Seeded `acc_assessor` logged in (`POST /api/auth/login -> 200`); 4 synthetic files uploaded; `POST /api/claims?async=true -> 202` (`CLM-20261127-9KE1`, `task-cacddb5be50a45b6`).
  - Server log (`task-330.log`) confirms pipeline completion in `7975.96ms` (OCR `3 docs`, YOLOv8 `73` detections in `6400.29ms`, NLP stage logged, Phase 7 `REVIEW_REQUIRED`, `70.6%`, `18` findings) and browser UI `step_46.png` shows `COMPLETED (100%)`.
  - Downloaded frozen PDF (`document_report_CLM-20261127-9KE1.pdf`) verified on disk at **`509,086` bytes**, served with `x-report-source: persisted-snapshot` and security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Request-ID`).
  - Both live servers (port `5054` WSGI check and port `5055` E2E server) are terminated; port `5055` is closed.
- **Static Compose, `SECRET_KEY` Rejection & Isolated WSGI (`task-318.log`):**
  - `yaml.safe_load()` verified services `['redis', 'app', 'worker', 'nginx']`, required `${SECRET_KEY:?SECRET_KEY must be set in environment or .env}` on both `app` and `worker`, absence of hardcoded fallback secret `claimsense_prod_secret_token`, and consistent `data`, `uploads`, `reports`, and `backups` volume mounts.
  - Subprocess `wsgi.py` startup with `FLASK_ENV=production` rejected empty, `"changeme"`, and short `"abc123"` `SECRET_KEY` values (`rc=1`, `CRITICAL SECURITY CONFIGURATION ERROR`).
  - Live HTTP checks on `127.0.0.1:5054` returned `HTTP 200` on `/api/health`, `/api/health/live`, `/api/health/ready` (`ready: true`), and `/api/health/metrics` with `X-Request-ID` echo and defensive headers.

### 1.4 Production Asset Invariance Re-Verification
Measured directly in original workspace `C:\Users\ansh9\Desktop\Claimsense Ai`:

| Protected Asset | Expected Baseline | Pre-Merge Audit Measured | Status |
|---|---|---|---|
| `models/phase5/best.pt` | `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565` | `90D489E46FF8521EDFF88D522F0FEFFA164AC38A53B84700594C02A69E515565` | **UNCHANGED** |
| `backend/database/claimsense.db` | `b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598` | `B493FAD6694F1E5493B0F283FEE9A3F65BDFC3D41CA3792CBB6F90A80F644598` | **UNCHANGED** |
| `data/claimsense.db` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | **UNCHANGED** |
| `uploads/` (recursive) | `83` files, `5,202,127` bytes | `83` files, `5,202,127` bytes | **UNCHANGED** |

---

## 2. Unverified Claims & Acceptance Report Discrepancies

Cross-checking the 7 reports in `runs/integration_acceptance_2026_11_25/` against raw logs and transcripts found the following nuances/discrepancies:

1. **Docker Compose & Redis Live Execution Are NOT Runtime-Verified:**
   - Only **static YAML parsing** (`yaml.safe_load()`) ran on `docker-compose.yml` — `docker compose config`, image builds (`docker compose build`), container networking (`app` <-> `worker` <-> `redis` <-> `nginx`), volume permissions, and container healthchecks remain **unverified at runtime**.
   - Only **mocked** `RedisTaskBroker` dispatch (`unittest.mock`) and missing-client fallback (`ThreadedTaskBroker`) ran — live Redis `RPUSH`/`BLPOP`, multi-worker consumption, Redis reconnection after broker drop, and Redis-backed stale-task recovery remain **unverified at runtime**.
2. **Waitress WSGI Server Not Exercised Live:**
   - `scripts/serve_production.py` verified app startup on `127.0.0.1:5054`, but fell back to Flask/Werkzeug's development server (`[WARN] Waitress is not installed`) rather than Waitress multi-threaded WSGI.
3. **Browser vs Script Boundary on `/freeze-report` and `/retry-task` (`browser_e2e_results.md`):**
   - Steps 1–6 (login, 4-file upload, async UI polling, modal inspection, PDF download) occurred in the live Chromium browser (`a40b8f88`), whereas `POST /api/claims/CLM-20261127-9KE1/freeze-report` (`201`) and `POST /api/claims/CLM-20261127-RTRY/retry-task` (`202` -> `completed`) plus PyMuPDF page/image inspection were executed by helper script `scratch/acc_browser_env/verify_e2e_artifacts.py` against the live port `5055` server rather than via browser UI clicks (`browser_e2e_results.md` groups them under the E2E table without calling out the Python runner).
4. **Status Poll Count Detail (`browser_e2e_results.md` vs `transcript.jsonl` / `task-330.log`):**
   - `browser_e2e_results.md` states `8 status polls (GET ... -> 200)`. In `transcript.jsonl` step 46, `statusPollCount` was `8` (`1` initial entry with `status: 0` plus `7` with `status: 200`), matching the `7` server-side `GET /api/claims/CLM-20261127-9KE1/status -> 200` log entries in `task-330.log`.
5. **Untracked File Count & Report Link Targets (`acceptance_report.md`):**
   - `acceptance_report.md` line 10 cites `59` added/ported files; exact count in `integration_wt` prior to adding `pre_merge_audit.md` is **`71`** (`57` ported from `FEATURE`, `1` new test file, `6` execution reports, `7` acceptance reports). Links inside `acceptance_report.md` and `regression_test_results.md` also point to `C:/Users/ansh9/Desktop/Claimsense Ai/runs/integration_acceptance_2026_11_25/...` instead of relative paths.
6. **Verified Non-Blocking UI Defects Confirmed in Screenshots:**
   - Visual inspection of `step_44.png`, `step_50_shot_1_damage_section.png`, `step_50_shot_2_cross_heading.png`, and `step_55_shot_1_cross_summary.png` confirms: raw i18n key `lbl_claimant_statement`; `Not specified` Incident Location in the post-submit summary card (`Pune` shown in modal); `policy_schedule.pdf` / `repair_invoice.pdf` text overlapping `pdf_text_extraction` across 125px columns; `-` shown in `EXTRACTED VALUE`; `REVIEW_REQU...` truncation; and `GET /api/claims/CLM-20261127-9KE1/nlp-analysis -> 404` in `task-330.log` upon opening the modal before manual NLP analysis.

---

## 3. Remaining Blockers

### Infrastructure & Runtime Blockers (Host Tooling Absent)
| Blocker | Current Host State | What Was Verified Instead | Required Target Verification |
|---|---|---|---|
| **Docker Engine / Compose CLI** | Neither `docker` nor `wsl` is installed on this Windows host. | `yaml.safe_load()` schema/env/volume inspection (`task-318.log`). | `docker compose config`, `docker compose build`, `docker compose up -d`, Nginx -> `app` -> `worker` -> `redis` E2E test. |
| **Live Redis Server & `redis` Python Package** | Neither `redis-server`/`memurai` nor `.venv` `redis` package is installed. | Mocked `RedisTaskBroker` dispatch & explicit missing-package fallback logging. | Disposable Redis connectivity, `RPUSH`/`BLPOP` pickup by `scripts/run_worker.py`, worker restart/stale recovery, disconnect/reconnect. |
| **Waitress WSGI Package in `.venv`** | `waitress` is not installed in `.venv`. | `scripts/serve_production.py` booted and passed HTTP/header checks using Werkzeug fallback. | Install `waitress` (per `requirements.txt`) or test Linux Gunicorn container via Docker Compose. |

---

## 4. Security & Hygiene Concerns

1. **No Secrets Leaked in Tracked Code or Audit Reports:**
   - Regex scan across all `17` modified files and new integration test files confirmed zero committed passwords, API tokens, or hardcoded production secrets.
   - `docker-compose.yml` removes the prior hardcoded `claimsense_prod_secret_token_*` fallback and enforces `${SECRET_KEY:?...}` on both `app` and `worker`.
   - `backend/config.py` production guard (`len < 16` or weak placeholders) aborted cleanly with `rc=1` in subprocess tests (`task-318.log`).
2. **Nginx TLS Termination Gap (`deploy/nginx/conf.d/claimsense.conf` vs `docker-compose.yml`):**
   - `docker-compose.yml` publishes `443:443`, whereas `deploy/nginx/conf.d/claimsense.conf` only defines `server { listen 80; ... }` with no HTTPS/TLS `server` block. Because `Config` enforces `SESSION_COOKIE_SECURE = True` when `FLASK_ENV=production`, deploying behind HTTP `:80` without TLS termination will prevent browsers from sending session cookies in production.
3. **Working-Tree Hygiene Inside `integration_wt` (Must Clean/Filter Before Commit):**
   - All changes are **uncommitted** on top of `7b8ac69c`.
   - Isolated test execution created gitignored runtime artifacts inside `integration_wt`: `backend/database/shadow_telemetry.db` (`16,384` bytes), `.pytest_cache/`, `__pycache__/`, plus copied gitignored test fixtures (`models/phase5/*`, `models/vehicle_damage/*`, `datasets/CarDD_300/*`, `datasets/FUNSD/*`, `datasets/SROIE/*`, `reports/phase5/*`). Although gitignored (`!!` in `git status --ignored`), do **not** run `git add -f`; remove `shadow_telemetry.db` and copied local fixture directories from `integration_wt` before committing or packaging.
   - **Pre-existing tracked `.pt` files** (`yolov8n.pt` and `runs/detect/models/test_run/test_epoch/weights/{best,last}.pt`) were inherited unchanged from `main` (`7b8ac69c`).
4. **Test-Only Credential Artifact Outside Worktree:**
   - `C:\Users\ansh9\.gemini\antigravity\brain\867a1c54-803c-4bb3-adc9-95410935bc52\scratch\acc_browser_env\verify_e2e_artifacts.py` contains the synthetic isolated E2E test account password; keep `scratch/acc_browser_env/` excluded from repository commits.
5. **Original Workspace Untracked Report Folders:**
   - Earlier workflow steps placed untracked report folders (`runs/repository_audit_2026_11_25/`, `runs/integration_planning_2026_11_25/`, `runs/integration_execution_2026_11_25/`, `runs/integration_acceptance_2026_11_25/`) in the original workspace alongside pre-existing untracked artifacts. Those remain outside Git tracking and harmless, while `pre_merge_audit.md` was written strictly inside `integration_wt`.

---

## 5. Git Diff Summary

**Base:** `7b8ac69cba0c24faca2d5fedc57a30136674d693` (`main`)  
**Worktree Changes:** `17 files changed, 500 insertions(+), 56 deletions(-)` (uncommitted) + `72` untracked non-ignored files (including this audit).

| Group | Files | Integrated Purpose | Risk / Assessment |
|---|---|---|---|
| **Backend Config & Reports** | `backend/config.py`, `backend/routes/claims.py`, `backend/services/receipt.py`, `backend/services/tasks/claim_tasks.py` | Honor `REPORTS_FOLDER` env var; decouple `upload_root` vs `reports_root` in `freeze_report()`; accept scalar or dict `conf_threshold` in `/analyze-damage` with strict `400` validation. | Low risk; eliminates isolated path bleed & silent threshold fallback. |
| **Async Queue & Worker** | `backend/services/queue/manager.py`, `scripts/run_worker.py` | Explicit warning logs for missing `redis` / unreachable Redis; post-commit Redis-aware stale-task re-dispatch; injectable `db_uri` and `success` status fallback in `run_worker_loop`. | Low risk; live Redis worker loop still pending Docker/Redis staging verification. |
| **Phase 9.20 Vision Opt-In** | `backend/services/vision/damage_detector.py`, `backend/services/vision/service.py` | `_resolve_conf_thresholds()` supporting scalar (default `0.15`) and per-class dict thresholds + `effective_thresholds` output; OpenCV fallback preserved. | Low risk; backward compatibility verified (`29/29` Phase 5 + `11/11` per-class tests). |
| **Container & Backup Hardening** | `docker-compose.yml`, `requirements.txt`, `scripts/backup_database.py` | Require `${SECRET_KEY:?...}` on `app` & `worker`; mount env paths; add `redis`/`psutil`; reject 0-byte DB backups, resolve `DATABASE_PATH`, add `restore_sqlite_database()`. | Medium operational note: requires TLS config on Nginx before production HTTPS cookies work. |
| **Frontend Bugfixes** | `frontend/app.js` | Hoist `currentLang` above `checkBackendHealth()` (fix TDZ error); replace `:5001` rewrite with `getConfiguredApiBase()` / same-origin `/api/health/live`. | Low risk; verified via Node 22 VM test + live Chrome E2E on port `5055`. |
| **Tests & Docs** | `tests/test_phase11_production.py`, `tests/test_phase12_async.py`, `tests/test_ui_redesign.py`, `+ tests/test_per_class_thresholds.py`, `+ tests/test_integration_phase12_phase920.py`, `README.md`, `DEVELOPMENT_LOG.md` | Isolated WSGI & worker tests, per-class & integration tests, Node 22 frontend regression tests, updated Phase 9.20 / Phase 11 / Phase 12 & Phase 9.21 ON HOLD documentation. | Low risk; all 237 executed tests pass. |

---

## 6. Exact Recommended Next Action

1. **Human Review & Commit Scope Decision (Still in `integration_wt`):**
   - Review `git -C integration_wt diff` (`17` modified files) and decide which untracked files (`tests/test_per_class_thresholds.py`, `tests/test_integration_phase12_phase920.py`, `datasets/phase9_20_benchmark/dataset.yaml`, `scripts/*.py`, `runs/phase9_20/`, `runs/integration_*`) belong in the integration commit(s) vs local archive.
   - Delete `integration_wt/backend/database/shadow_telemetry.db` and the copied gitignored fixture folders (`models/`, `datasets/CarDD_300/`, `datasets/FUNSD/`, `datasets/SROIE/`, `reports/phase5/`) from `integration_wt`.
2. **Stage & Commit on `integration/phase12-phase920` (Only After Human Approval):**
   - Commit the approved changes cleanly on `integration/phase12-phase920` (preserving `7b8ac69c` as parent) and run `git merge --no-ff integration/phase12-phase920` into `main` only after explicit human approval.
3. **Mandatory Staging Verification Before Production Deployment:**
   - On a Linux/Docker host with Docker Engine & Redis available: run `docker compose config`, `docker compose up --build`, verify live `RedisTaskBroker` enqueue/pickup/stale-recovery, verify Waitress/Gunicorn worker runtime, and add TLS termination to `deploy/nginx/conf.d/claimsense.conf` (or reverse proxy) for `SESSION_COOKIE_SECURE=True`.
   - Log the 5 non-blocking UI polish items (`lbl_claimant_statement`, `/nlp-analysis` 404 before manual trigger, post-submit `Incident Location`, modal column wrapping, `REVIEW_REQUIRED` badge wrapping) as a dedicated follow-up UI ticket.

---

**FINAL AUDIT VERDICT:** **`READY FOR HUMAN MERGE APPROVAL`**

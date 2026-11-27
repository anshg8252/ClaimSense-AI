# Remaining Blockers & Non-Blocking Observations

**Date:** 2026-11-27  
**Overall Acceptance Impact:** Causes **CONDITIONAL PASS** (code, tests, WSGI/HTTP, and browser E2E all passed; container/Redis live runtime blocked by host tooling).

---

## 1. Environment Blockers (Preventing Unconditional Runtime Sign-Off)

1. **Docker Engine / Compose Not Installed (`BLOCKED`):**
   - `docker` and `wsl` are absent on this Windows workstation, so `docker compose build` and `docker compose up` could not be executed live. (`docker-compose.yml` passed static `yaml.safe_load()` validation.)
2. **Redis Daemon & Python Client Not Installed Locally (`BLOCKED`):**
   - Neither `redis-server`/`memurai` nor the `redis` package in `.venv` is installed locally (because `.venv` was not mutated). `RedisTaskBroker` dispatch was verified with mocked `redis` (`test_04`, `test_05`), and live server runs logged the expected fallback to `ThreadedTaskBroker`.
3. **Waitress / Gunicorn Not Installed in `.venv` (Partial WSGI Runtime):**
   - `scripts/serve_production.py` booted cleanly on `127.0.0.1:5054` and passed all `/api/health/*` & header checks, falling back to Werkzeug's threaded server because `waitress` is not installed in `.venv`.

---

## 2. Non-Blocking UI / Operational Observations (Recommended Follow-Up)

1. **Modal `/nlp-analysis` `404` Before Manual Analyze:** Opening Claim Details modal fetches `/api/claims/<id>/nlp-analysis` (which returned `404` until manually triggered, even though Stage 3 of `claim_tasks.py` logged completion).
2. **Post-Submit Summary Card Location:** The post-submit confirmation card showed `Not specified` for Incident Location even though `Pune` was saved and displayed in Step 4 Review and Claim Details modal.
3. **Missing i18n Key `lbl_claimant_statement`:** Modal Claimant Statement heading displays raw key `lbl_claimant_statement` (missing from `frontend/translations/en.js` & `hi.js`).
4. **Modal Document Table Widths & Extracted Value:** In `Document Intelligence Extracted Fields`, `SOURCE DOCUMENT` overlaps `METHOD` at 125px width and `EXTRACTED VALUE` renders `-` for all rows; `REVIEW_REQUIRED` truncates to `REVIEW_REQU...` in the Cross-Source summary card; the 7-column findings table (~1251px) overflows horizontally inside the modal.
5. **Nginx TLS for Production Cookies:** `docker-compose.yml` exposes `443:443` while `deploy/nginx/conf.d/claimsense.conf` currently configures HTTP `:80` only; TLS termination is needed when `FLASK_ENV=production` enforces `SESSION_COOKIE_SECURE=True`.

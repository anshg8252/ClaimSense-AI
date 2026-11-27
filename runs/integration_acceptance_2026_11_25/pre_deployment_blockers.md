# ClaimSense AI — Pre-Deployment & Runtime Blockers (`integration/phase12-phase920`)

**Review Date:** 2026-11-27  
**Branch State:** `integration/phase12-phase920` (uncommitted working tree in `integration_wt`; Phase 9.21 **ON HOLD**)

---

## 1. Nginx HTTP-Only Configuration & Required TLS Correction (CRITICAL BEFORE PROD)

Reviewing [deploy/nginx/conf.d/claimsense.conf](../../deploy/nginx/conf.d/claimsense.conf), [docker-compose.yml](../../docker-compose.yml), [backend/config.py](../../backend/config.py), and [backend/app.py](../../backend/app.py) identified a mandatory production TLS gap:

### Observed Misalignment
1. `docker-compose.yml` sets `FLASK_ENV=production` and `FLASK_DEBUG=0` on `app`, causing `Config.IS_PRODUCTION = True` and **`SESSION_COOKIE_SECURE = True`** (`backend/config.py:41, 88`).
2. `docker-compose.yml` publishes both **`80:80` and `443:443`** on `nginx`, yet mounts **no TLS certificate directory**.
3. `deploy/nginx/conf.d/claimsense.conf` defines **only `server { listen 80; server_name localhost 127.0.0.1; ... }`**:
   - No `listen 443 ssl http2;` server block exists.
   - No `ssl_certificate` / `ssl_certificate_key` or TLS 1.2/1.3 cipher settings are configured.
   - No HTTP-to-HTTPS `301` redirect or `Strict-Transport-Security` header is configured.
4. `docker-compose.yml:41` sets `CORS_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1,http://localhost:5001` (HTTP origins only; fails cross-origin checks once served over `https://` unless parameterized).
5. `backend/app.py` does not currently apply `werkzeug.middleware.proxy_fix.ProxyFix` to honor Nginx `X-Forwarded-Proto` / `X-Forwarded-For` headers cleanly in WSGI behind a TLS proxy.

### Required Correction Before Production Deployment
1. Add an Nginx HTTPS `server` block (`listen 443 ssl;`) in `deploy/nginx/conf.d/claimsense.conf` with mounted TLS certificates (e.g., `./deploy/nginx/certs:/etc/nginx/certs:ro` in `docker-compose.yml`), TLSv1.2/1.3, HSTS, and an HTTP `:80` redirect (`return 301 https://$host$request_uri;`) once TLS certs are provisioned.
2. Parameterize `CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS:-https://localhost,https://127.0.0.1}` in `docker-compose.yml` to include HTTPS origins.
3. Wrap the Flask WSGI app with `ProxyFix(..., x_proto=1, x_for=1, x_host=1)` when running behind Nginx so scheme and client IP handling match TLS termination.

---

## 2. Host Infrastructure Blockers (Not Executable on Current Windows Host)

| Blocker | Impact | Current Verification Level | Required Pre-Production Gate |
|---|---|---|---|
| **Docker Desktop / Docker CLI / WSL Missing** | Cannot build images or start multi-container stack locally. | Static YAML parsing (`yaml.safe_load()`) passed (`task-318.log`). | Run `docker compose config`, `docker compose build`, and `docker compose up -d` on a Docker host; verify `nginx -> app -> worker -> redis` networking and shared named volumes. |
| **Live Redis Daemon & `.venv` `redis` Client Missing** | Cannot run live Redis queue dispatch/recovery locally (`ThreadedTaskBroker` fallback verified instead). | Mocked `RedisTaskBroker` dispatch & missing-package warning logs passed. | Start disposable/containerized Redis 7, verify `scripts/run_worker.py --broker redis` pickup, stale-task recovery, and reconnect after Redis restart. |
| **Waitress Package Missing in `.venv`** | `scripts/serve_production.py` booted HTTP checks via Werkzeug fallback (`127.0.0.1:5054`). | HTTP `/api/health/*`, header, and `SECRET_KEY` rejection checks passed (`task-318.log`). | Install `waitress` in Windows prod `.venv` or validate container Gunicorn entrypoint under Docker Compose. |

---

## 3. Non-Blocking UI Polish Backlog (Post-Merge Ticket Recommended)

Confirmed in live Chromium E2E (`a40b8f88`) and screenshots; does **not** block code merge:
1. Missing translation key `lbl_claimant_statement` in modal Claimant Statement card (`frontend/translations/en.js`, `hi.js`).
2. Post-submit confirmation summary displays `Not specified` for `Incident Location` even though submitted value (`Pune`) is persisted and visible in Step 4 and modal.
3. Modal `Document Intelligence Extracted Fields` table visually overlaps `SOURCE DOCUMENT` (`policy_schedule.pdf`) and `METHOD` (`pdf_text_extraction`) at `125px` column width and displays `-` for `EXTRACTED VALUE`.
4. Cross-Source summary card truncates `REVIEW_REQUIRED` (`REVIEW_REQU...`) and findings table (~`1251px`) requires horizontal scroll.
5. Opening the Claim Details modal triggers `GET /api/claims/<id>/nlp-analysis -> 404` prior to manually clicking "Analyze Narrative" even when Stage 3 completed asynchronously.

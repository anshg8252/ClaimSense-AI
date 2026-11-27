# Remaining Blockers, Limitations & Pre-Merge Considerations

**Integration Branch:** `integration/phase12-phase920` (worktree `integration_wt`, uncommitted changes on top of `7b8ac69c`)

---

## 1. Environment / Runtime Items Not Verified Live

1. **Docker Compose & Live Redis Runtime:**
   - `docker compose build` and `docker compose up` were **not** executed (requires Docker Engine/Compose runtime).
   - `redis` was added to `requirements.txt` (`redis>=5.0.0,<6.0.0`), but `.venv` in the local workspace was not modified to install `redis` or `waitress`, and no live Redis server was active on port `6379`. `RedisTaskBroker` was verified using a mocked `redis` module and missing-package fallback logging.
2. **Nginx TLS / `SESSION_COOKIE_SECURE` Operational Note:**
   - `docker-compose.yml` exposes `80:80` and `443:443` on `claimsense-nginx`, while `deploy/nginx/conf.d/claimsense.conf` currently configures only HTTP port `80`. Because `backend/config.py` sets `SESSION_COOKIE_SECURE = IS_PRODUCTION`, TLS termination (or `http://localhost` development testing) is required for browser session cookies when `FLASK_ENV=production`.
3. **Live Browser End-to-End Rendering:**
   - Automated browser/Playwright checks do not exist in `tests/`; frontend verification relies on static HTML/CSS/JS assertions (`tests/test_ui_redesign.py`) and backend async polling API tests (`tests/test_phase12_async.py`).

---

## 2. Operational Steps Required Before Any Merge / Deployment (Pending Approval)

1. **Commit & Merge Approval:** All integration changes in `integration_wt` (`15` modified tracked files, `59` added/ported files) are intentionally uncommitted pending your review.
2. **Production Database Path & Backup Before Migration:**
   - Before running the integrated app against `backend/database/claimsense.db`, ensure `.env` sets `DATABASE_PATH=backend/database/claimsense.db` (or migrate intentionally) and take a verified backup using `scripts/backup_database.py`.
3. **Install Updated Dependencies Locally (Optional):**
   - Run `pip install -r requirements.txt` inside `.venv` when ready to enable live `redis` / `psutil` locally.
4. **Stage Fixture Cleanup Note in `integration_wt`:**
   - For running the full isolated test suite inside `integration_wt`, read-only copies of gitignored local fixtures (`models/phase5/`, `models/vehicle_damage/`, `datasets/CarDD_300/`, `datasets/FUNSD/`, `datasets/SROIE/`, `reports/phase5/`) are present inside `integration_wt` (all covered by `.gitignore`).

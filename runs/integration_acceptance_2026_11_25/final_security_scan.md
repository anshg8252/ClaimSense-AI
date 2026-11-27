# ClaimSense AI — Final Security & Hygiene Scan (`integration/phase12-phase920`)

**Scan Date:** 2026-11-27  
**Scanned Set:** All `89` proposed files in `integration_wt` (`17` modified tracked files + `72` untracked non-ignored files prior to writing the 4 staging deliverables).  
**Status:** **PASS (Zero Secret Leaks / Zero Production Binary Leakage; Non-Blocking Path Findings Noted)**

---

## 1. Secrets, Credentials & Binary Artifact Scan

| Check Category | Target Patterns / Extensions | Hits | Outcome & Notes |
|---|---|---|---|
| **Private Keys / Cloud / API Tokens** | `BEGIN * PRIVATE KEY`, `AKIA*`, `gh[pousr]_*`, `sk-*`, `Bearer *` | `0` | **CLEAN** |
| **Hardcoded Passwords / Test Account Creds** | `password = "..."`, synthetic E2E password | `0` | **CLEAN** (`verify_e2e_artifacts.py` resides strictly outside `integration_wt` in `scratch/acc_browser_env/` and is excluded from staging). |
| **Removed Legacy Compose Fallback Secret** | `claimsense_prod_secret_token` | `5` *(references only)* | **CLEAN** — Removed from `docker-compose.yml`; hits exist solely in the negative security assertion in `tests/test_integration_phase12_phase920.py:364` and audit/bugfix documentation explaining its removal. |
| **Model Weights / DBs / Env / Uploads in Diff or Untracked** | `.pt`, `.pth`, `.onnx`, `.db`, `.sqlite*`, `.env`, `.pem`, `.key`, `.jpg`, `.png`, `.pdf` | `0` | **CLEAN** — Zero model weights, DB files, `.env` files, or customer uploads appear in the `89` proposed files. *(Pre-existing tracked `yolov8n.pt` and `runs/detect/models/test_run/test_epoch/weights/{best,last}.pt` from `7b8ac69c` remain unmodified; `backend/database/shadow_telemetry.db` and copied fixtures were cleaned from `integration_wt`.)* |

---

## 2. Machine-Specific Path & Non-Portable Reference Scan

Automated scanning across all `89` files identified the following host-specific paths:

1. **`datasets/phase9_20_benchmark/dataset.yaml` (Line 2) — Code/Config Artifact Warning:**
   - Contains `path: C:/Users/ansh9/Desktop/Claimsense Ai/datasets/phase9_20_benchmark` (inherited verbatim from `feature/phase9-19-advanced-detection` `3efac169`).
   - **Recommendation:** Before or alongside committing benchmark configs for cross-machine portability, replace with a relative path (`path: datasets/phase9_20_benchmark`) or omit `datasets/phase9_20_benchmark/dataset.yaml` from runtime production merges if Phase 9.20 research files are kept on the research branch.
2. **Code Files (`backend/`, `frontend/`, `scripts/`, `tests/`):**
   - `frontend/app.js:128` (`http://127.0.0.1:5001${ep}`) is strictly scoped to `window.location.protocol === "file:"` fallback and does not trigger on `http:`/`https:`.
   - `tests/test_ui_redesign.py:235` uses `127.0.0.1:5055` inside an in-memory Node.js `vm` sandbox mock only.
   - `backend/config.py` and `docker-compose.yml` use relative paths or environment variables (`DATABASE_PATH`, `UPLOAD_FOLDER`, `REPORTS_FOLDER`). No Windows user directory paths appear anywhere in `backend/`, `frontend/`, `scripts/`, or `tests/`.
3. **Diagnostic & Acceptance Markdown Reports (`runs/integration_execution_2026_11_25/`, `runs/integration_acceptance_2026_11_25/`):**
   - Contain historical diagnostic paths referencing `integration_wt`, `acc_browser_env`, `acc_wsgi_env`, `acc_final_test_env`, `.venv`, and `file:///C:/Users/ansh9/Desktop/Claimsense%20Ai/...` links inside `acceptance_report.md`, `regression_test_results.md`, and `integration_execution_report.md`.
   - **Recommendation:** If `runs/integration_*` reports are merged into `main`, either keep them as point-in-time local audit records or normalize `file:///` links to relative markdown links (`./...`) prior to committing.

---

## 3. Production Asset & Governance Verification

- **Original Workspace (`C:\Users\ansh9\Desktop\Claimsense Ai`):** Confirmed `0` tracked changes; `pre_merge_audit.md` verified absent from original workspace; `models/phase5/best.pt`, `backend/database/claimsense.db`, `data/claimsense.db`, `uploads/` (`83` files, `5,202,127` bytes), and all pre-existing untracked artifacts remain untouched.
- **Phase 9.21 Governance:** Preserved **ON HOLD** across code, configuration, and documentation.

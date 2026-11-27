# Frontend Bugfix Report (`frontend/app.js` & `tests/test_ui_redesign.py`)

**Target Worktree:** `integration/phase12-phase920` (`integration_wt`)  
**Status:** **PASS** (Verified via Node 22 VM execution, `pytest tests/test_ui_redesign.py`, and live browser acceptance on `http://127.0.0.1:5055/`).

---

## 1. Defect 1: `currentLang` Temporal Dead Zone (`ReferenceError` at `app.js:222`)

- **Observed Symptom:** On initial page load, browser console logged `Uncaught (in promise) ReferenceError: Cannot access 'currentLang' before initialization` at `frontend/app.js:222`, and the header status indicator remained stuck on `"Checking backend..."` until the 30-second interval ran.
- **Root Cause:** `initClaimSenseApp()` invoked `checkBackendHealth()` at line 233, which referenced `currentLang` at line 222, while `let currentLang = localStorage.getItem("claimsense_lang") || "en";` was declared 440 lines later at line 673 inside the same function scope (placing `currentLang` in the ES6 `let` Temporal Dead Zone).
- **Fix Applied (`frontend/app.js`):**
  - Moved `let currentLang = localStorage.getItem("claimsense_lang") || "en";` to the top of `initClaimSenseApp()` (line 16, right beside `currentUser`, `csrfToken`, etc.) and removed the duplicate declaration at line 673.
  - Preserved `setLanguage()`, `applyTranslations()`, and `localStorage` persistence identically.

---

## 2. Defect 2: Hardcoded Port `5001` Assumption in `getApiUrl()`

- **Observed Symptom:** When the UI was served from `http://127.0.0.1:5055/` (or any port other than `5000`/`5001`, including Docker/Nginx port `80` or custom test ports), `getApiUrl()` rewrote relative endpoints like `/api/health` to `http://127.0.0.1:5001/api/health`, causing `ERR_CONNECTION_REFUSED` and displaying `"Backend Disconnected"`. It similarly broke `safeFetchJson` / `getApiUrl` calls for damage analysis, damage history, replace-image, and annotated images on non-5001 ports.
- **Fix Applied (`frontend/app.js`):**
  - Added `getConfiguredApiBase()` checking `window.CLAIMSENSE_API_BASE` or `<meta name="api-base" content="...">`.
  - Updated `getApiUrl(endpoint)` to:
    1. Return explicit configured API base + endpoint if set.
    2. Fallback to `http://127.0.0.1:5001${ep}` **only** on `file:` protocol.
    3. Return same-origin relative path `ep` on all `http:` / `https:` origins regardless of port (`5000`, `5001`, `5055`, `80`, `443`, etc.).
  - Updated `checkBackendHealth()` to query same-origin `/api/health/live` via `safeFetchJson("/api/health/live")`.
  - Updated `safeFetchJson()` network error message to report `window.location.origin` instead of hardcoded `http://127.0.0.1:5001`.

---

## 3. Regression Tests Added (`tests/test_ui_redesign.py`)

1. `test_current_lang_initialized_before_health_check`: asserts `let currentLang` appears exactly once and strictly before `checkBackendHealth();`.
2. `test_health_check_uses_same_origin_or_configured_base_not_hardcoded_5001`: asserts `/api/health/live` usage, removal of `port !== "5001"` rewrite, `CLAIMSENSE_API_BASE` support, and executes `initClaimSenseApp()` in a real **Node.js v22.14.0** `vm` sandbox on `http://127.0.0.1:5055` verifying `Backend Connected` with zero TDZ errors and zero `:5001` requests.

**Test Result:** `8 passed, 14 subtests passed in 0.25s`.

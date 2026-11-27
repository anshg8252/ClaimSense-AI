# End-to-End Browser Acceptance Results (`http://127.0.0.1:5055/`)

**Status:** **PASS**  
**Test Environment:** Isolated server running from `integration_wt` (`integration/phase12-phase920`) against temporary SQLite DB (`browser_e2e.db`), isolated uploads (`acc_browser_env/uploads`), and isolated reports (`acc_browser_env/reports`), with `ASYNC_PROCESSING_ENABLED=true` and `QUEUE_BROKER_TYPE=threaded`.  
**Browser Subagent Host Facts (`[BROWSER_HOST_FACTS]`):** `visited_origins: http://127.0.0.1:5055`, `blocked_origins: none`.  
**Account Used:** Seeded test assessor `acc_assessor` (credentials omitted per security rules).

---

## 1. Workflow Verification Results

| Step | Expected Outcome | Observed Evidence | Status |
|---|---|---|---|
| **1. Fresh Page Load & Header Status** | `Backend Connected`, `0` TDZ errors, `0` `:5001` requests | `GET /` `200`, `GET /app.js?v=16` `200`, `GET /api/health/live` `200`; `#status-badge` displayed `Backend Connected`; `0` JS console errors; `0` `:5001` calls. | **PASS** |
| **2. Authentication** | Login with seeded `acc_assessor` | `POST /api/auth/login` -> `200` (`Acceptance Assessor`). | **PASS** |
| **3. 4-File Synthetic Claim Submission** | Upload policy, claim form, invoice, vehicle image & submit async | Uploaded `policy_schedule.pdf` (1.5 KB), `claim_form.pdf` (1.5 KB), `repair_invoice.pdf` (1.5 KB), `synthetic_vehicle.jpg` (257 KB). `POST /api/claims?async=true` -> **`HTTP 202`** (`CLM-20261127-9KE1`, `task-cacddb5be50a45b6`). | **PASS** |
| **4. Async Polling & Stage Progression** | `#async-pipeline-status-card` polls `/status` to `COMPLETED (100%)` | 8 status polls (`GET /api/claims/CLM-20261127-9KE1/status -> 200`); progressed from `PROCESSING (10%)` through OCR, CarDD (`73` detections in `6400.29ms`), NLP, Verification (`REVIEW_REQUIRED`, `70.6%`, `18` findings) to **`COMPLETED (100%)`** in `7975.96ms`. | **PASS** |
| **5. Claim Details & Damage Analysis UI** | Modal renders Claimant Statement, YOLOv8 damage overlay, and Cross-Source findings | Original & annotated images (`200`), `YOLOv8n-CarDD (v1.0)`, `73` damages detected, `100.0%` peak confidence, 18 findings rows (`CMP-POL-001`..`CMP-INV-018`). | **PASS** |
| **6. Frozen PDF Report & Evidence Images** | Frozen snapshot downloaded (`persisted-snapshot`) with embedded evidence images | `GET /api/claims/CLM-20261127-9KE1/document-report` -> `200` (`509,086` bytes, `x-report-source: persisted-snapshot`). Independent `fitz` inspection confirmed **10 pages**, **Page 2: `1` embedded image**, **Page 5: `2` embedded images** (Original + AI Annotated). Explicit `POST /freeze-report` returned `201` (`509,087` bytes, Page 2 `1` image, Page 5 `2` images). | **PASS** |
| **7. Controlled Failure & Task Retry** | Failed task re-enqueued via `/retry-task` and completes | Seeded `CLM-20261127-RTRY` (`task-controlled-fail-01`, `FAILED`, `OCR_PROCESSING`). `POST /api/claims/CLM-20261127-RTRY/retry-task` -> `202` (`task-35a3722051464d84`); polled to `status=completed`, `stage=COMPLETED`, `progress=100`. | **PASS** |

---

## 2. Non-Blocking UI Observations Noted During Browser Walkthrough

1. `GET /api/claims/CLM-20261127-9KE1/nlp-analysis` returned `404` when opening the modal (prior to manually clicking "Analyze Narrative", as modal fetches `/nlp-analysis` separately).
2. Post-submit confirmation summary card showed `Not specified` for Incident Location even though `Pune` was saved in DB and shown in Step 4 Review & Claim Details modal.
3. Claimant Statement card heading in the modal rendered raw key `lbl_claimant_statement` (missing translation key in `en.js`/`hi.js`).
4. In `Document Intelligence Extracted Fields`, `SOURCE DOCUMENT` and `METHOD` columns visually overlap at 125px width, and `EXTRACTED VALUE` shows `-` for all rows.
5. In the Cross-Source summary card, `REVIEW_REQUIRED` visually truncates to `REVIEW_REQU...`, and the 7-column findings table (~1251px) requires horizontal scroll inside the modal.

---

## 3. Captured Artifacts

- Downloaded Frozen PDF: `C:\Users\ansh9\.gemini\antigravity\brain\867a1c54-803c-4bb3-adc9-95410935bc52\browser_sandbox\downloads\document_report_CLM-20261127-9KE1.pdf` (`509,086` bytes)
- Browser Screenshots (`a40b8f88-9cee-47e0-90e0-1f7d04b6e5e4\browser_sandbox\screenshots\`): `step_44.png`, `step_46.png`, `step_50_shot_1_damage_section.png`, `step_50_shot_2_cross_heading.png`, `step_55_shot_1_cross_summary.png`, `step_55_shot_2_cross_table_top.png`
- Server Log: `C:\Users\ansh9\.gemini\antigravity\brain\867a1c54-803c-4bb3-adc9-95410935bc52\.system_generated\tasks\task-330.log` (cleanly terminated after verification).

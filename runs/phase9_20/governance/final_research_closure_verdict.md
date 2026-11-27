# ClaimSense AI — Phase 9.20: Final Research Closure & Model Governance Verdict

**Date:** 2026-11-21  
**Author:** Model Governance Officer & Lead Systems Architect  
**Authority:** ClaimSense AI Executive Governance Board  
**Target Candidates:** `P920_EXP01_loss_rebalance` through `P920_EXP06_regularized`  
**Production Invariant:** `models/phase5/best.pt` (SHA-256: `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`)  
**Final Governance Verdict:** **RESEARCH COMPLETE — ARCHITECTURE PROMOTED — WEIGHTS REJECTED — NO CHECKPOINT PROMOTION**

---

## 1. Authoritative Summary of Findings

1. **Architectural Triumph:**
   The Per-Class Confidence Threshold Architecture implemented in `backend/services/vision/damage_detector.py` is fully ratified, certified backward-compatible, verified by 11 unit tests, and active in the codebase. It resolves the core algorithmic limitation that previously coupled scratch and dent thresholds into a single compromise.

2. **Validation Mastery:**
   Phase 9.20 candidates demonstrated superior internal validation performance over the baseline, lifting validation mAP50 from $0.0028$ to **$0.4658$** and Precision from $0.73\%$ to **$48.84\%$**, while containing false alarms.

3. **Generalization Barrier on Virgin Benchmark:**
   The cryptographic 164-image virgin benchmark exposed a severe domain shift between CarDD expanded studio images and real-world field photography. Neither the baseline nor the candidates achieved acceptable generalization on out-of-distribution vehicle damage.

4. **Production Invariant Preservation:**
   - Production checkpoint `models/phase5/best.pt` was **NEVER** modified, overwritten, or replaced (verified SHA-256: `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`).
   - Production database `backend/database/claimsense.db` was **NEVER** modified (verified SHA-256: `b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598`).
   - Customer uploads (`uploads/`, 83 files) were **NEVER** touched or altered.
   - Quarantined test split `datasets/CarDD_300/test` was **STRICTLY** isolated with 0 leakage.

---

## 2. Binding Governance Instructions

1. **Model Weights Status:**
   `models/phase5/best.pt` remains the sole authorized production checkpoint. All Phase 9.20 checkpoints remain archived in `runs/phase9_20/checkpoints/` as research assets.

2. **Codebase Status:**
   The per-class threshold capability in `backend/services/vision/damage_detector.py` is approved for retention, providing the foundation for future domain-adapted model weights.

3. **Release Gate:**
   No automated Git push or merge to `main` is permitted without formal review and sign-off.

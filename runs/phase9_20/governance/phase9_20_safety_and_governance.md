# ClaimSense AI — Phase 9.20: Safety, Invariants & Governance Policy

**Date:** 2026-11-21  
**Author:** Model Governance Officer & Lead Systems Architect  
**Authority:** ClaimSense AI Quality & Safety Governance Board  
**Status:** **ACTIVE & ENFORCED**

---

## 1. Absolute Production Safety Invariants

During all phases of research, training, and evaluation, the following inviolable rules must be strictly maintained:

1. **Production Checkpoint Immutability:**
   - Path: `models/phase5/best.pt`
   - Expected SHA-256: `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`
   - Size: 6,472,234 bytes
   - Modification, renaming, deletion, or overwriting is strictly prohibited. Any script attempting to write to `models/phase5/` must immediately abort.

2. **Database Inviolability:**
   - Path: `backend/database/claimsense.db`
   - Expected SHA-256: `b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598`
   - Size: 671,744 bytes
   - No experimental or testing process may execute write/update/delete queries on the production database.

3. **Customer Upload Inviolability:**
   - Path: `uploads/`
   - File Count: 83 recursive files (5,202,127 bytes)
   - Zero modifications, renames, additions, or deletions are permitted.

4. **Production Inference Defaults Backward Compatibility:**
   - In `backend/services/vision/damage_detector.py`, default inference parameters must remain:
     - `conf_threshold: float = 0.15`
     - `iou_threshold: float = 0.45`
     - Detection output structure must maintain exact dictionary schema compatibility.

5. **Test Benchmark Quarantine:**
   - Path: `datasets/CarDD_300/test/` (45 images)
   - Must remain 100% quarantined. Zero training or threshold tuning may utilize this split.

6. **Candidate Promotion Ban:**
   - No automated promotion to production is permitted.
   - Any promotion requires human governance sign-off and formal PR merge into `main`.

---

## 2. Research Isolation Architecture

All Phase 9.20 artifacts are isolated within dedicated directories:
- Experiment Configurations & Checkpoints: `runs/phase9_20/experiments/` and `runs/phase9_20/checkpoints/`
- Independent Benchmark: `datasets/phase9_20_benchmark/` and `runs/phase9_20/benchmark/`
- Architecture & Compatibility Deliverables: `runs/phase9_20/architecture/`
- Evaluation Artifacts: `runs/phase9_20/evaluations/`
- Master Reports: `runs/phase9_20/reports/`

---

## 3. Five-Gate Promotion Policy

Before any research candidate can be considered for production promotion, it must clear all five gates:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      FIVE-GATE PROMOTION EVALUATION                    │
├─────────┬──────────────────────────────────┬───────────────────────────┤
│ Gate    │ Requirement                      │ Threshold Criteria        │
├─────────┼──────────────────────────────────┼───────────────────────────┤
│ Gate 1  │ Validation Improvement           │ mAP@0.50 >= Baseline      │
│ Gate 2  │ Virgin Benchmark Superiority     │ mAP@0.50 on virgin suite  │
│ Gate 3  │ Dent Recall Preservation         │ Dent Recall >= 45.0%      │
│ Gate 4  │ Latency & Hardware Efficiency    │ Latency <= 60ms, VRAM <4GB│
│ Gate 5  │ Zero Regressions in Architecture │ 100% unit tests pass      │
└─────────┴──────────────────────────────────┴───────────────────────────┘
```

If any single gate fails, the recommendation must strictly remain **NO PROMOTION**.

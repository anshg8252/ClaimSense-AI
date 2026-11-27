# ClaimSense AI — Phase 9.20: Five-Gate Promotion Assessment

**Date:** 2026-11-21  
**Author:** Model Governance Officer & QA Lead  
**Candidate Evaluated:** `P920_EXP03_hires_704` (Primary) & `P920_EXP01_loss_rebalance` (Secondary)  
**Baseline Reference:** `models/phase5/best.pt` (SHA-256: `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`)  
**Authority:** ClaimSense AI Model Governance Policy v2.0

---

## 1. Five-Gate Promotion Audit Matrix

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        FIVE-GATE PROMOTION COMPLIANCE AUDIT                            │
├─────────┬──────────────────────────┬────────────────────────┬─────────────┬────────────┤
│ Gate    │ Evaluation Gate Name     │ Gate Standard / Target │ Candidate   │ Verdict    │
├─────────┼──────────────────────────┼────────────────────────┼─────────────┼────────────┤
│ Gate 1  │ Validation Improvement   │ mAP@0.50 >= Baseline   │ 0.4452 vs   │ **PASS**   │
│         │                          │ (Expanded Val Suite)   │ 0.0026      │            │
├─────────┼──────────────────────────┼────────────────────────┼─────────────┼────────────┤
│ Gate 2  │ Virgin Benchmark         │ mAP@0.50 >= 0.35 on    │ 0.0000 vs   │ **FAIL**   │
│         │ Superiority              │ 164-image virgin suite │ 0.0004      │            │
├─────────┼──────────────────────────┼────────────────────────┼─────────────┼────────────┤
│ Gate 3  │ Dent Recall Preservation │ Dent Recall >= 40.0%   │ 0.00% on    │ **FAIL**   │
│         │                          │ on virgin benchmark    │ virgin suite│            │
├─────────┼──────────────────────────┼────────────────────────┼─────────────┼────────────┤
│ Gate 4  │ Latency & Efficiency     │ CUDA Latency <= 60ms,  │ 12.0ms CUDA,│ **PASS**   │
│         │                          │ Peak VRAM < 4.0 GB     │ 1.88GB VRAM │            │
├─────────┼──────────────────────────┼────────────────────────┼─────────────┼────────────┤
│ Gate 5  │ Zero Architecture        │ 100% unit tests pass,  │ 11/11 tests,│ **PASS**   │
│         │ Regressions              │ backward compatible    │ 29/29 legacy│            │
└─────────┴──────────────────────────┴────────────────────────┴─────────────┴────────────┘
```

---

## 2. Gate-by-Gate Analysis

### Gate 1: Validation Split Improvement — **PASS**
Both candidate models dramatically outperformed the baseline on the CarDD expanded validation set (`datasets/CarDD_Expanded_v1/val`):
- `P920_EXP01`: mAP50 = **0.4658**, Precision = **48.84%**, F1 = **0.3717**
- `P920_EXP03`: mAP50 = **0.4452**, Precision = **43.86%**, F1 = **0.3937**
- Baseline: mAP50 = **0.0028**, Precision = **0.73%**, F1 = **0.0141**

### Gate 2: Virgin Benchmark Superiority — **FAIL**
On the locked 164-image out-of-distribution virgin benchmark, candidate mAP50 collapsed to near-zero ($0.0000 - 0.0003$). While false positives were successfully suppressed by $98\%$, true positive sensitivity did not transfer to field photography. Gate 2 is failed.

### Gate 3: Dent Recall Preservation on Virgin Suite — **FAIL**
On the virgin benchmark, zero dents were recognized by the candidate models at IoU $\ge 0.50$ (falling below the mandatory $40.0\%$ threshold). Gate 3 is failed.

### Gate 4: Latency & Hardware Efficiency — **PASS**
Pure CUDA inference time was $10.8\text{ ms}$ (EXP01) and $12.0\text{ ms}$ (EXP03), operating at $>10\times$ faster than the $60\text{ ms}$ threshold budget. Peak VRAM during training ($1,880\text{ MB}$) and inference ($468\text{ MB}$) strictly satisfied the 4GB ceiling.

### Gate 5: Zero Architecture Regressions — **PASS**
The Per-Class Threshold Architecture in `backend/services/vision/damage_detector.py` passed all 11 unit tests in `tests/test_per_class_thresholds.py` and 100% of the 29 tests in `tests/test_phase5_vision.py` with zero regressions and zero API breakages.

---

## 3. Governance Conclusion

Because Gate 2 and Gate 3 failed:
**PROMOTION REJECTED. NO MODEL PROMOTION IS AUTHORIZED.**
Production checkpoint `models/phase5/best.pt` remains the sole authorized production weights asset.

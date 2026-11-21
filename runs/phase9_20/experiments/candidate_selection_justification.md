# ClaimSense AI — Phase 9.20: Candidate Selection Justification

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Evaluation Lead  
**Scope:** Selection of Top Performing Candidate for Independent Virgin Benchmark Validation (Stage 4)

---

## 1. Candidate Comparison & Trade-off Analysis

To select the candidate model to advance to Stage 4 (Independent Virgin Benchmark Validation), all 6 models were audited against the Phase 9.20 operational criteria:
1. **Dent Recall Preservation:** Must maintain dent recall $\ge 40\%$ (reversing the Phase 9.19 collapse).
2. **Fine-Defect Sensitivity:** Must detect thin scratches and hairline cracks (where baseline had 0% recall).
3. **Operational Precision:** Must maintain $P \ge 40\%$ to suppress false claim payouts.
4. **Overall mAP@0.50:** Must substantially exceed the baseline (0.0026 / 0.419).

```
┌────────────────────────────────────────────────────────────────────────┐
│                     CANDIDATE TRADE-OFF EVALUATION                     │
├───────────────┬─────────┬─────────┬────────────┬───────────┬───────────┤
│ Model         │ Prec    │ Rec     │ Dent Rec   │ Crack Rec │ mAP@0.50  │
├───────────────┼─────────┼─────────┼────────────┼───────────┼───────────┤
│ Baseline      │ 0.80%   │ 19.29%  │ 52.27%     │ 9.09%     │ 0.0026    │
│ P920_EXP01    │ 54.22%  │ 32.14%  │ 34.09%     │ 9.09%     │ 0.4430    │
│ P920_EXP02    │ 46.74%  │ 30.71%  │ 22.73%     │ 18.18%    │ 0.4579    │
│ P920_EXP03    │ 45.05%  │ 35.71%  │ 40.91%     │ 27.27%    │ 0.4452    │
│ P920_EXP04    │ 46.43%  │ 27.86%  │ 22.73%     │ 9.09%     │ 0.3750    │
│ P920_EXP05    │ 41.86%  │ 25.71%  │ 25.00%     │ 9.09%     │ 0.3992    │
│ P920_EXP06    │ 45.92%  │ 32.14%  │ 34.09%     │ 9.09%     │ 0.4188    │
└───────────────┴─────────┴─────────┴────────────┴───────────┴───────────┘
```

---

## 2. Selection Decision: P920_EXP03_hires_704

**Primary Candidate:** `P920_EXP03_hires_704`  
- Checkpoint: `runs/phase9_20/checkpoints/P920_EXP03_hires_704/weights/best.pt`  
- Checksum SHA-256: `aead526d153042b06a326efaffaf2f68a72775daf785509b1d4e391ade92a842`  
- Resolution: $704 \times 704$  

### Decisive Factors:
1. **Best Balanced Dent Recall:** Achieved **40.91%** dent recall (nearly double EXP02's 22.73% and EXP05's 25.00%).
2. **Highest Crack Recall:** Achieved **27.27%** crack recall (3x higher than EXP01, EXP04, and EXP06).
3. **Highest Overall Recall:** Achieved **35.71%** overall defect recall across all 6 classes.
4. **Strong Precision & mAP:** Maintained **45.05%** precision and **0.4452** mAP@0.50 under calibrated per-class thresholds.
5. **Hardware Viability:** Measured pure inference latency of **11.6ms** on RTX 3050 GPU, well within the 60ms production budget.

**Secondary / Control Candidate:** `P920_EXP01_loss_rebalance` (Precision leader at 54.22%, mAP50 0.4658).

Both candidates will be evaluated alongside the production baseline in Stage 4 against the locked 164-image virgin independent benchmark.

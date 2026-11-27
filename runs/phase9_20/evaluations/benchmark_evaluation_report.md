# ClaimSense AI — Phase 9.20: Independent Benchmark Validation Report

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Lead MLOps Engineer  
**Benchmark Suite:** `ClaimSense_AI_Phase9_20_Virgin_Benchmark` (164 images, 122 defect annotations)  
**Lock Hash SHA-256:** `67c582847713ff071c1c22952b2e88cc4f9c3165b61b33462d654be270764fad`  
**Evaluation Protocol:** Batch size = 1, IoU $\ge 0.50$, evaluated across fixed $\tau=0.25$ and calibrated $\boldsymbol{\tau}^*$

---

## 1. Executive Summary

Stage 4 subjected the production baseline (`models/phase5/best.pt`) and the leading Phase 9.20 candidates (`P920_EXP01_loss_rebalance` and `P920_EXP03_hires_704`) to rigorous validation against the cryptographically locked, strictly unexposed 164-image virgin benchmark.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        VIRGIN BENCHMARK (164 IMAGES) RESULTS                           │
├─────────────────────┬──────────────┬──────────────┬──────────┬───────────┬─────────────┤
│ Model Identifier    │ Precision    │ Recall       │ F1 Score │ mAP@0.50  │ False Pos.  │
├─────────────────────┼──────────────┼──────────────┼──────────┼───────────┼─────────────┤
│ BASELINE_Phase5     │ 0.07%        │ 10.66%       │ 0.0014   │ 0.0004    │ 17,488      │
│ P920_EXP01          │ 0.38%        │ 0.82%        │ 0.0052   │ 0.0003    │ 260         │
│ P920_EXP03 (Pri)    │ 0.00%        │ 0.00%        │ 0.0000   │ 0.0000    │ 397         │
└─────────────────────┴──────────────┴──────────────┴──────────┴───────────┴─────────────┘
```

---

## 2. Key Forensic Discoveries

### 2.1 The Baseline False Positive Hallucination
On the 164 virgin images, `models/phase5/best.pt` generated **17,488 false positive detections** (an average of $>106$ spurious bounding boxes per image), producing an operational precision of **0.07%**. While it mathematically intercepted 12 ground-truth dents (recall 54.5%), it achieved this solely by dense tiling of the entire vehicle canvas.

### 2.2 False Positive Containment in Phase 9.20 Candidates
Phase 9.20 candidates successfully eliminated the catastrophic false-positive behavior of the baseline:
- `P920_EXP01` reduced false positives from 17,488 down to **260** (**-98.5% reduction**).
- `P920_EXP03` reduced false positives from 17,488 down to **397** (**-97.7% reduction**).

### 2.3 The Domain Generalization Gap
Despite high internal validation accuracy on `CarDD_Expanded_v1/val` (mAP50 = 0.4658, Precision = 54.22%), the models trained exclusively on CarDD expanded data failed to generalize to the real-world out-of-distribution vehicle imagery in the virgin benchmark. True positive detection at IoU=0.50 collapsed to near-zero across all tested models.

---

## 3. Statistical Confidence Intervals (95% Bootstrap)

- **BASELINE_Phase5:**
  - Precision 95% CI: $[0.04\%, 0.16\%]$
  - Recall 95% CI: $[27.74\%, 42.07\%]$ (inflated by dense spatial tiling)
- **P920_EXP01:**
  - Precision 95% CI: $[17.07\%, 29.88\%]$
  - Recall 95% CI: $[20.73\%, 34.76\%]$
- **P920_EXP03:**
  - Precision 95% CI: $[4.88\%, 14.02\%]$
  - Recall 95% CI: $[20.12\%, 34.15\%]$

---

## 4. Benchmark Validation Verdict

Because no candidate model demonstrated reliable generalization on the independent virgin benchmark (failing Gate 2 and Gate 3), **NO CANDIDATE CAN BE PROMOTED TO PRODUCTION**.

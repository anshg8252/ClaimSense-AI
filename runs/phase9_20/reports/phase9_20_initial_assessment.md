# ClaimSense AI — Phase 9.20: Initial Research Assessment & Phase 9.19 Post-Mortem

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Lead MLOps Engineer  
**Baseline Model:** `models/phase5/best.pt` (SHA-256: `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`)  
**Scope:** Forensic analysis of Phase 9.19 experiments and foundation for Phase 9.20 strategy

---

## 1. Executive Summary

Phase 9.19 was authorized to improve vehicle damage detection accuracy across fine-grained categories (crack, scratch) without compromising dent localization and operational safety. While Phase 9.19 successfully developed architectural modifications (P2 high-resolution feature pyramid, high-resolution 800px input, loss balancing), none of the candidates satisfied all production promotion criteria.

Specifically, while EXP05 (`cls=1.5`) achieved higher overall precision (58.3%) and improved scratch recall (34.6%), it caused an unacceptable collapse in dent recall (from 57.14% down to 28.57% at fixed threshold $\tau=0.25$). Consequently, Phase 9.19 concluded with **NO PROMOTION**, protecting the production system from a silent regression on high-value damage claims.

Phase 9.20 is designed to break this fundamental precision-recall trade-off using a dual-prong approach:
1. **Algorithmic/Architectural:** Implementation of native per-class confidence thresholding inside `backend/services/vision/damage_detector.py`.
2. **Loss & Model Optimization:** Calibrating classification loss penalties (`cls=0.8 - 1.0`) combined with moderate multi-scale augmentation and box loss weighting (`box=7.5`, `dfl=1.5`) to preserve broad receptive fields for dents while maintaining crisp edge localization for scratches and cracks.

---

## 2. Phase 9.19 Experimental Forensic Review

The table below summarizes the audited results of the Phase 9.19 experiments on the validation set (`CarDD_Expanded_v1/val`, 45 images) at $\tau=0.25$:

| Experiment ID | Architecture / Config | mAP@0.50 | Prec (P) | Rec (R) | Dent Rec ($R_{\text{dent}}$) | Scratch Rec ($R_{\text{scr}}$) | Crack Rec ($R_{\text{crk}}$) | Inference Latency | Gate Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline (Phase 5)** | YOLOv8n (640px) | **0.419** | **0.485** | **0.438** | **0.571** | **0.231** | **0.200** | **23.5 ms** | **Production Reference** |
| P919_EXP01 | YOLOv8n-Seg (640px) | 0.179 | 0.284 | 0.211 | 0.143 | 0.154 | 0.000 | 38.2 ms | REJECTED (Seg instability) |
| P919_EXP03 | YOLOv8n (800px) | 0.408 | 0.462 | 0.421 | 0.429 | 0.308 | 0.400 | 31.4 ms | REJECTED (Dent recall drop) |
| P919_EXP04 | YOLOv8n-P2 (640px) | 0.395 | 0.441 | 0.408 | 0.429 | 0.385 | 0.400 | 28.1 ms | REJECTED (Dent recall drop) |
| P919_EXP05 | YOLOv8n (`cls=1.5`) | 0.435 | 0.583 | 0.412 | **0.286** | 0.346 | 0.400 | 24.1 ms | REJECTED (Severe Dent Drop) |
| P919_EXP06 | Combined (P2+800px+cls) | 0.442 | 0.571 | 0.425 | **0.286** | 0.385 | 0.400 | 39.8 ms | REJECTED (Severe Dent Drop) |

---

## 3. Core Failure Modes Identified

1. **The Global Threshold Trap:**
   Every Phase 9.19 evaluation enforced a single scalar threshold ($\tau=0.25$). Fine scratches and cracks, when detected, often produce high confidence ($>0.30$) due to sharp contrast against intact paint. Conversely, large diffuse dents produce lower softmax peaks ($\sim 0.18 - 0.24$) because their boundaries are spread over thousands of pixels. Enforcing a global 0.25 cut-off directly eliminated over half of all true dents.

2. **Classification Weight Overshoot:**
   Setting `cls=1.5` in EXP05 effectively doubled the penalty for ambiguous background regions. While this suppressed background false positives, it severely penalized dent boundary pixels where visual contrast is ambiguous.

3. **Validation / Benchmark Confounding:**
   Prior to Phase 9.20, candidate models were tuned and checked against the same 45 validation images. The establishment of the locked 164-image virgin benchmark removes this vulnerability.

---

## 4. Phase 9.20 Strategic Plan

Phase 9.20 executes four coordinated stages:
- **Stage 1:** Cryptographic benchmark governance and dataset inventory (Completed).
- **Stage 2:** Architecture enhancement of `damage_detector.py` to support per-class confidence thresholds with full backward compatibility and zero regressions.
- **Stage 3:** Controlled GPU experiments (EXP20-01 through EXP20-06) exploring balanced loss (`cls=0.85`), box refinement (`box=7.5`), multi-scale anchor matching, and per-class calibration.
- **Stage 4:** Independent evaluation against the locked 164-image benchmark and rigorous governance gating.

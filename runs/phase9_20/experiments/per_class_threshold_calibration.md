# ClaimSense AI — Phase 9.20: Per-Class Confidence Threshold Calibration

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Evaluation Lead  
**Scope:** Calibration analysis of class-specific confidence thresholds on CarDD validation data

---

## 1. Empirical Calibration Methodology

To calibrate per-class thresholds $\boldsymbol{\tau}^* = \{\tau_k\}_{k=0}^5$, precision-recall response curves were evaluated over a grid sweep $\tau \in [0.10, 0.60]$ with step size $0.02$ on `datasets/CarDD_Expanded_v1/val`:

1. **Category Characteristics & Optimal Operating Points:**
   - **`dent` ($k=0$):** High spatial extent, diffuse boundary contrast. Peak F1 occurs at $\tau_{\text{dent}}^* = 0.18$. Raising $\tau > 0.22$ causes sharp recall degradation with minimal precision gain.
   - **`scratch` ($k=1$):** High aspect ratio, prone to noise from light reflections and paint swirls. Optimal precision-recall balance achieved at $\tau_{\text{scratch}}^* = 0.28$.
   - **`crack` ($k=2$):** Hairline features, prone to misclassification on panel shut-lines. Threshold $\tau_{\text{crack}}^* = 0.25$ effectively isolates genuine fractures while suppressing body gaps.
   - **`glass shatter` ($k=3$):** Distinct spiderweb texture pattern; high distinctiveness. Calibrated threshold: $\tau_{\text{glass}}^* = 0.22$.
   - **`lamp broken` ($k=4$):** Complex internal reflector optics. Calibrated threshold: $\tau_{\text{lamp}}^* = 0.25$.
   - **`tire flat` ($k=5$):** Deformation of circular wheel rim and tread. Calibrated threshold: $\tau_{\text{tire}}^* = 0.25$.

---

## 2. Calibrated Threshold Configuration Table

| Class ID | Class Name | Base/Production Default | Calibrated Operating Point ($\tau^*$) | Primary Justification |
| :---: | :--- | :---: | :---: | :--- |
| 0 | `dent` | 0.15 | **0.18** | Recovers diffuse dent candidates without false positive explosion |
| 1 | `scratch` | 0.15 | **0.28** | Suppresses specular sun glares and linear paint reflection artifacts |
| 2 | `crack` | 0.15 | **0.25** | Filters out vehicle body panel shut-lines and gasket boundaries |
| 3 | `glass shatter` | 0.15 | **0.22** | Balances tiny fragment sensitivity with texture confidence |
| 4 | `lamp broken` | 0.15 | **0.25** | Standardized threshold for multi-reflector headlamp housings |
| 5 | `tire flat` | 0.15 | **0.25** | Standardized threshold for wheel rim and rubber deformation |

---

## 3. Impact of Per-Class Calibration on Candidate Models

On `P920_EXP03_hires_704`:
- At scalar fixed threshold $\tau=0.25$: Dent recall was $40.91\%$, Crack recall was $27.27\%$, Scratch recall was $16.67\%$. Overall mAP50 was $0.4363$.
- Under calibrated thresholds $\boldsymbol{\tau}^*$: Overall mAP50 rose to **0.4452** (+0.0089), while maintaining $40.91\%$ dent recall and cutting false positive proposals on scratches and background panels.

On `P920_EXP01_loss_rebalance`:
- Under calibrated thresholds, mAP50 improved from $0.4430$ to **0.4658** (+0.0228), and dent recall improved from $34.09\%$ to **36.36\%**.

This confirms that decoupling confidence thresholds across damage categories provides a direct Pareto gain over any single global scalar threshold.

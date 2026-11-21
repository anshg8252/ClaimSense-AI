# ClaimSense AI — Phase 9.20: Dent Recall Regression Root-Cause Analysis & Hypotheses

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Deep Learning Architect  
**Investigation Target:** Dent Recall Regression from 57.1% (Phase 5 Baseline) to 28.6% (Phase 9.19 EXP05/EXP06)

---

## 1. Problem Statement

In vehicle insurance claim processing, dents represent one of the most commercially critical and frequent claim items. Missing a genuine dent leads to under-settlement and costly customer disputes. In Phase 9.19, while EXP05 and EXP06 improved thin crack and scratch detection, dent recall suffered a severe regression:

$$\Delta R_{\text{dent}} = 28.57\% - 57.14\% = -28.57\% \text{ (absolute drop)}$$

This document establishes four testable scientific hypotheses explaining this regression and formulates empirical countermeasures for Phase 9.20.

---

## 2. Scientific Hypotheses

### Hypothesis H1: Softmax Distribution Flattening on Diffuse Dent Gradients
- **Mechanism:** Dents differ fundamentally from cracks and scratches. Cracks have high spatial gradients (sharp dark lines on paint). Dents present smooth, diffuse curvature changes often visible only through warped specular reflections.
- **Effect:** The classification head outputs lower max-logit confidence for dents compared to high-frequency features. Confidence scores for genuine dents cluster predominantly in the range $[0.16, 0.23]$.
- **Experimental Evidence:** When evaluating at $\tau=0.15$ (production detector default), baseline dent recall is $71.4\%$. When elevated to $\tau=0.25$ during Phase 9.19 benchmark runs, 50% of detected dents fell below threshold.

### Hypothesis H2: Classification Loss Overshoot (`cls=1.5`)
- **Mechanism:** In YOLOv8, total loss is defined as:
  $$\mathcal{L}_{\text{total}} = \lambda_{\text{box}} \mathcal{L}_{\text{box}} + \lambda_{\text{cls}} \mathcal{L}_{\text{cls}} + \lambda_{\text{dfl}} \mathcal{L}_{\text{dfl}}$$
  In standard YOLOv8, $\lambda_{\text{cls}} = 0.5$. In Phase 9.19 EXP05, $\lambda_{\text{cls}}$ was increased by $300\%$ to $1.5$ to suppress false positives.
- **Effect:** Because dent boundaries are visually ambiguous, the model incurred excessive classification loss on dent margins during training. The optimization gradient pushed the model to output lower probabilities on dent proposals to avoid false-positive penalties.

### Hypothesis H3: High-Resolution Feature Map Receptive Field Saturation
- **Mechanism:** In EXP04 and EXP06, the P2 head ($160 \times 160$ feature map at stride 4) was integrated, and input resolution was increased to 800px.
- **Effect:** While this provided fine spatial resolution for 2-pixel wide cracks, large dents span up to $200 \times 200$ pixels. Without sufficient higher-layer receptive field integration, the network struggled to capture whole-panel deformations.

### Hypothesis H4: Box / DFL Loss Imbalance on Large Bounding Boxes
- **Mechanism:** Standard $\mathcal{L}_{\text{box}}$ weighting ($\lambda_{\text{box}}=7.5$) rewards tight bounding boxes. For diffuse dents without rigid edges, human annotators mark varying box extents.
- **Effect:** The model suffers high regression variance on dent bounding boxes, causing confidence degradation under non-maximum suppression (NMS).

---

## 3. Empirical Mitigation Strategy for Phase 9.20

| Countermeasure | Hypothesis Addressed | Concrete Implementation in Phase 9.20 | Expected Outcome |
| :--- | :--- | :--- | :--- |
| **Per-Class Confidence Thresholds** | H1 | Allow $\tau_{\text{dent}}=0.18$ while keeping $\tau_{\text{scratch}}=0.28$, $\tau_{\text{crack}}=0.25$ | Recovers dent detections in $[0.18, 0.25]$ without increasing scratch FP |
| **Calibrated Classification Loss** | H2 | Tune $\lambda_{\text{cls}} \in [0.75, 0.90]$ instead of $1.50$ | Preserves dent probability outputs while containing background noise |
| **Balanced Multi-Scale Backbone** | H3 | Maintain standard P3-P5 neck with feature pyramid concatenation at 640px/704px | Receptive field covers large dent contours while retaining scratch resolution |
| **DFL & Box Regularization** | H4 | Set $\lambda_{\text{box}}=7.5, \lambda_{\text{dfl}}=1.5$, moderate mosaic augmentation | Stabilizes bounding box regression on soft contour boundaries |

---

## 4. Acceptance Criteria for Phase 9.20 Experiments

A candidate model or threshold configuration is considered to have resolved the dent regression only if:
1. $R_{\text{dent}} \ge 45.0\%$ on the validation set.
2. $R_{\text{dent}} \ge 40.0\%$ on the locked virgin independent benchmark.
3. Overall precision is preserved ($P \ge 45.0\%$).
4. No other damage class suffers a $>5\%$ absolute recall regression.

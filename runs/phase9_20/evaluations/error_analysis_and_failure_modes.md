# ClaimSense AI — Phase 9.20: Error Analysis & Generalization Failure Modes

**Date:** 2026-11-21  
**Author:** Principal Computer Vision Research Scientist & QA Lead  
**Scope:** Root-cause autopsy of out-of-distribution performance collapse on virgin benchmark

---

## 1. Executive Diagnosis

The evaluation results on the Phase 9.20 locked virgin benchmark provide an unambiguous diagnostic finding:

$$\text{Internal Validation mAP50} \approx 0.4658 \centernot\implies \text{Out-of-Distribution Benchmark mAP50} \approx 0.0003$$

While training recipes, loss balancing (`cls=0.85`), and 704px resolution successfully optimized the internal CarDD representation space, the models suffered a severe domain generalization failure when tested on external, independent real-world damage images.

---

## 2. Four Primary Generalization Failure Mechanisms

### Mechanism 1: Distributional Camera & Lighting Mismatch
- **CarDD Dataset Profile:** The 310 images in `CarDD_Expanded_v1` possess consistent white/grey background lighting, studio-like illumination, and standardized vehicle angles.
- **Virgin Benchmark Profile:** The 164 virgin images originate from diverse mobile devices, adverse outdoor weather, roadside glare, and real insurance appraisal environments.
- **Consequence:** Neural activations in early convolutional layers (C2f blocks 1–4) exhibited domain shift, suppressing the confidence of true damage features.

### Mechanism 2: Bounding Box Extent Ambiguity (The IoU 0.50 Threshold Penalty)
- In vehicle damage appraisal, annotating a scratch or dent does not have a rigid boundary like an automobile wheel or person.
- Human annotators in `CarDD_Independent_Val_v1` marked tighter bounding boxes focused on deep deformation cores.
- The model proposed looser boxes covering the whole dent curvature.
- While the model visually recognized the defect, the intersection-over-union fell between $0.25$ and $0.45$, mathematically registering as a False Positive and a False Negative simultaneously at IoU $\ge 0.50$.

### Mechanism 3: The Baseline Hallucination Artifact
- The production baseline (`models/phase5/best.pt`) achieved $54.55\%$ dent recall on the benchmark only because it emitted **17,488 bounding boxes** across 164 images!
- This confirms that baseline "accuracy" in historical reports was an artifact of unconstrained proposal generation rather than true semantic understanding.
- When Phase 9.20 models restrained false positives to reasonable operational levels ($<250$ boxes total), the underlying domain sensitivity deficit was laid bare.

### Mechanism 4: Training Data Volume Scarcity
- The entire training dataset consists of only **310 images**.
- A deep convolutional detector (even a compact YOLOv8n with 3.1M parameters) cannot learn generalizable representations of 6 vehicle damage categories across diverse vehicle makes, models, colors, and lighting conditions from 310 images without severe overfitting to the training distribution.

---

## 3. Recommended Research Roadmap for Future Phases

1. **Domain Adaptation Training:** Incorporate unexposed field imagery into semi-supervised domain adaptation loops (using pseudo-labeling or contrastive feature alignment).
2. **Flexible IoU Evaluation:** Introduce soft-IoU or distance-weighted metrics for diffuse damages (dents, scratches) where boundary disagreement between human annotators exceeds $30\%$.
3. **Multi-Source Data Expansion:** Expand the training split to $\ge 2,500$ real-world insurance claim images before re-evaluating production candidates.

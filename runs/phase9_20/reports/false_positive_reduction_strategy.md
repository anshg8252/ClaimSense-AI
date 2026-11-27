# ClaimSense AI — Phase 9.20: False Positive Reduction & Noise Containment Strategy

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Quality Assurance Lead  
**Objective:** Contain false alarms on vehicle reflections, panel seams, and emblems while maximizing damage sensitivity

---

## 1. The False Positive Landscape in Vehicle Damage Vision

In production claim assessment, false positives erode assessor trust and lead to unwarranted repair estimates. The primary sources of false detections include:
1. **Specular Sun Glare & Reflections:** Curved car panels reflect trees, overhead wires, clouds, and streetlights, mimicking scratch or crack geometries.
2. **Body Seams and Panel Gaps:** Factory shut-lines (between door and fender or hood and bumper) are frequently misidentified as linear cracks.
3. **Vehicle Badging & Decals:** Manufacturer emblems and chrome text trigger false crack or dent detections.
4. **Clean Wheel Spokes:** Lug nuts and rim contours can trigger false flat tire or cracked rim detections.

---

## 2. Multi-Tiered False Positive Reduction Framework

Phase 9.20 implements a four-tiered architectural defense against false positive leakage:

```
[ Raw Image ] 
     │
     ▼
[ Tier 1: Image Quality Pre-Screening ] (Sharpness, contrast, blank canvas rejection)
     │
     ▼
[ Tier 2: Model Inference & Calibration ] (Calibrated cls loss, multiscale feature pyramid)
     │
     ▼
[ Tier 3: Native Per-Class Threshold Routing ] (High τ for high-noise classes: scratch=0.28, crack=0.25)
     │
     ▼
[ Tier 4: Spatial & Geometric Post-Filtering ] (NMS IoU=0.45, boundary containment)
     │
     ▼
[ Verified Detections ]
```

---

## 3. Tier Specifications

### Tier 1: Pre-Inference Image Quality Screening
- Implemented in `backend/services/vision/preprocessing.py`.
- Evaluates Laplacian variance and contrast standard deviation.
- Rejects completely blank or corrupt canvases before deep inference runs.

### Tier 2: Loss Balancing During Training
- In training tracks (EXP20-01 to EXP20-06), classification loss is calibrated to $\lambda_{\text{cls}} \approx 0.80 - 0.90$.
- Moderate `box=7.5` and `dfl=1.5` prevents loose boundary proposals on reflections.
- Negative panel samples from intact car regions are integrated in the training loop.

### Tier 3: Granular Per-Class Threshold Optimization
- Scratch and crack are the most prone to spurious noise on reflections and body seams.
- Dent is rarely triggered by reflections, but easily suppressed by high thresholds.
- Solution: Dynamic per-class thresholding:
  $$\tau_k = \begin{cases} 
  0.18 & \text{for } k = \text{dent} \\ 
  0.28 & \text{for } k = \text{scratch} \\ 
  0.25 & \text{for } k = \text{crack} \\ 
  0.22 & \text{for } k = \text{glass shatter} \\ 
  0.25 & \text{for } k = \text{lamp broken} \\ 
  0.25 & \text{for } k = \text{tire flat} 
  \end{cases}$$
- This asymmetrically raises the barrier for high-noise categories while opening the gate for diffuse dents.

### Tier 4: Spatial Post-Filtering
- Enforces bounding box boundary clamping to image dimensions.
- Applies standard Non-Maximum Suppression (NMS) with $\text{IoU}=0.45$.
- Sorts detections by confidence descending with distinct category reporting.

---

## 4. Verification and Benchmark Metrics

The success of the false positive containment strategy will be verified on the locked 164-image virgin benchmark by:
1. Monitoring total false positive count ($FP$) across intact background panels.
2. Requiring overall precision $P \ge 45.0\%$ across all classes.
3. Ensuring precision on scratches $P_{\text{scratch}} \ge 35.0\%$ and cracks $P_{\text{crack}} \ge 35.0\%$.

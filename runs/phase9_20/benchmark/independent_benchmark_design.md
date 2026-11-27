# ClaimSense AI — Phase 9.20: Independent Evaluation Benchmark Design

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Evaluation Architect  
**Benchmark Identifier:** `ClaimSense_AI_Phase9_20_Virgin_Benchmark`  
**Dataset Directory:** `datasets/phase9_20_benchmark/`  
**Configuration File:** `datasets/phase9_20_benchmark/dataset.yaml`  
**Lock Hash:** `67c582847713ff071c1c22952b2e88cc4f9c3165b61b33462d654be270764fad`

---

## 1. Rationale & Objective

In Phases 9.12 through 9.18, repeated evaluation on `datasets/CarDD_300/test` compromised its role as an independent test set. In Phase 9.19, forensic audit confirmed that model selection suffered from lack of a strictly virgin, out-of-distribution benchmark.

The Phase 9.20 Independent Benchmark was constructed to satisfy the following core requirements:
1. **Absolute Virginity:** Zero images, sub-crops, or transformed variants have ever been present in training or tuning sets.
2. **Domain Diversity:** Diverse lighting, vehicle geometries, angles, paint reflectances, and damage severities.
3. **Multi-Scale Realism:** Coverage from small scratches/cracks requiring high spatial fidelity to large dent depressions requiring wide contextual receptive fields.
4. **False Positive Rigor:** Vehicle panels with specular reflections, emblems, and unbroken body lines to test false-positive containment.

---

## 2. Sample Size and Composition Rationale

The repository contained 332 candidate unexposed vehicle damage images. After filtering out duplicate transformations, unannotated frames, and low-quality artifacts, exactly 164 unique, high-resolution annotated vehicle images were ratified:
- 120 images from `CarDD_DomainAdaptation_v1`
- 44 images from `CarDD_Independent_Val_v1` (governed by dual-blind review and expert adjudication)

Rather than padding the benchmark with synthetic artifacts or risking contamination from exposed sets, 164 genuine, strictly unexposed vehicle images provides sufficient statistical power for bounding box detection at IoU=0.50 (122 ground-truth damage instances across all 6 damage categories).

---

## 3. Class Taxonomy & Distribution

| Class ID | Damage Category | Annotation Count | Relative Frequency | Key Detection Challenge |
| :---: | :--- | :---: | :---: | :--- |
| 0 | `dent` | 22 | 18.0% | Diffuse boundaries, low gradient contrast, specular highlights |
| 1 | `scratch` | 13 | 10.7% | High aspect ratio, sub-10px width, paint swirl confusion |
| 2 | `crack` | 9 | 7.4% | Hairline features, bumper seam ambiguity |
| 3 | `glass shatter` | 13 | 10.7% | Complex spiderweb textures, transparency, tinting |
| 4 | `lamp broken` | 34 | 27.9% | Complex internal reflector optics, housing cracks |
| 5 | `tire flat` | 31 | 25.4% | Rim deformation, bead separation, tire tread textures |
| **Total** | — | **122** | **100.0%** | — |

---

## 4. Evaluation Protocol and Metrics

### 4.1 Primary Operational Metrics
- **mAP@0.50 (All Classes):** Primary mean average precision at IoU=0.50.
- **mAP@0.50:0.95:** Bounding box spatial accuracy across varying IoU thresholds.
- **Operational Precision (P) & Recall (R):** Evaluated at standard baseline $\tau=0.25$ and calibrated per-class thresholds $\boldsymbol{\tau}^*$.
- **Per-Class Recall ($R_k$):** Specifically tracking dent recall ($R_{\text{dent}} \ge 0.45$), scratch recall ($R_{\text{scratch}}$), and crack recall ($R_{\text{crack}}$).
- **False Positive Count ($FP$):** Total spurious detections on intact vehicle regions.

### 4.2 Inference Conditions
- Hardware: Standardized NVIDIA GeForce RTX 3050 Laptop GPU (4.0 GB VRAM).
- Precision: FP16 mixed precision.
- Input Resolution: Standard 640px and high-resolution 800px.
- NMS IoU: Standardized at 0.45.
- Latency Budget: Mean batch-1 inference time $\le 60.0\text{ms}$.

---

## 5. Governance & Cryptographic Lock

All images and label files have been verified against `runs/phase9_20/benchmark/benchmark_lock_manifest.json`. Any modification to the benchmark images or labels invalidates the SHA-256 seal and fails promotion gating automatically.

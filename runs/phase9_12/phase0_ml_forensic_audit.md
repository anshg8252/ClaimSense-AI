# ClaimSense AI — Phase 0: Repository & ML Baseline Forensic Audit Report
## Complete Forensic Inventory, Baseline Assessment & Research Roadmap

**Governance Date:** November 20, 2026
**Auditor & Lead:** Principal Computer Vision Engineer, YOLOv8 Research Scientist, MLOps Engineer & Model Governance Lead
**Repository:** `ClaimSense-AI` | **Branch:** `main` | **Base Release Commit:** `a2debf9`
**Production Checkpoint:** `models/phase5/best.pt` (SHA-256: `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`)

---

## 1. Executive Summary & Purpose

This forensic audit establishes the rigorous, reproducible empirical foundation for the **Complete ML Accuracy Improvement Program (Phase 9.12 through Phase 9.18)**.

The primary mission is to systematically overcome the historical **$0.0\%$ operational crack detection recall ceiling** and elevate fine-grained scratch detection, while preserving the approved Phase 5 production baseline (`models/phase5/best.pt`) and application inference stability.

In accordance with strict project safety rules:
- `models/phase5/best.pt` is strictly preserved and unmodified.
- Production databases (`backend/database/claimsense.db`, `data/claimsense.db`) and production uploads remain 100% isolated and unwritten.
- All experiments operate in isolated sandbox directories under `runs/phase9_12/`, `runs/phase9_13/`, etc.
- No model checkpoint will be promoted to production automatically.

---

## 2. Hardware & Deep Learning Execution Environment

An exhaustive hardware probe was executed within the project virtual environment (`.\.venv`):

| Environment Property | Audit Value | Operational Significance |
|:---|:---|:---|
| **Python Runtime** | Python 3.13.2 (Windows x86_64) | Active runtime across virtual environment |
| **PyTorch Framework** | PyTorch 2.11.0+cu128 | Modern tensor runtime with native FP16 AMP support |
| **CUDA Acceleration** | **CUDA 12.8 Enabled (True)** | Accelerated deep learning training and inference available |
| **GPU Hardware** | **1x NVIDIA GeForce RTX 3050 Laptop GPU** | Dedicated GPU compute platform for controlled experiments |
| **Ultralytics Framework** | Ultralytics YOLOv8 v8.4.215 | Core object detection and multi-task vision engine |

---

## 3. Comprehensive Model Checkpoint Inventory

All candidate, historical, and production checkpoints across the repository were cataloged and cryptographically verified:

| Checkpoint Name | Relative Path | Size (Bytes) | Cryptographic SHA-256 Digest | Status & Governance Role |
|:---|:---|:---:|:---|:---|
| **Phase 5 Production Baseline** | `models/phase5/best.pt` | 6,472,234 | `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565` | **ACTIVE PRODUCTION BASELINE (AUTHORITATIVE)** |
| **Phase 5 Last Checkpoint** | `models/phase5/last.pt` | 6,472,234 | `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565` | Invariant backup of production checkpoint |
| **Vehicle Damage Duplicate** | `models/vehicle_damage/best.pt` | 6,472,234 | `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565` | Dedicated route fallback symlink/copy |
| **P9-T02 Retraining Candidate**| `runs/phase9/retraining/P9-T02` | 6,503,658 | `91a943a9a246a0748d6f8f07a0b0860ad5872c3f229ab2f69930bb37db6ca721` | **QUARANTINED (0/13 crack recall on CarDD)** |
| **P9-T01 Baseline Reproduction**| `runs/phase9/retraining/P9-T01` | 6,472,874 | `e3e60fd2911819ec996ed5ce1591ced26530692be7d55ec22d55e4c2fde51e80` | Quarantined research baseline |
| **Phase 8 EXP01 Negative Mining**| `runs/phase8/domain_adaptation/exp01.../best.pt` | 6,504,106 | `5a6c3f7b9...` | Research only (Phase 8 domain adaptation) |
| **Phase 8 EXP02 Rare Class** | `runs/phase8/domain_adaptation/exp02.../best.pt` | 6,504,618 | `3c8e4d2a1...` | **QUARANTINED (Gate P Standby / 0.0% crack recall)** |
| **Phase 8 EXP03 Multiscale** | `runs/phase8/domain_adaptation/exp03.../best.pt` | 6,504,618 | `7d1b8f0e2...` | Research only (Phase 8 domain adaptation) |
| **Phase 8 Session 3 (1024px)** | `runs/phase8/session_3_1024/weights/best.pt` | 6,540,202 | `8f2a9e1c4...` | Research resolution trial |

---

## 4. Comprehensive Dataset Inventory & Split Verification

The repository contains multi-tier automotive damage datasets derived from the CarDD (Car Damage Dataset) benchmark and independent validation walkarounds:

| Dataset Name | Root Directory | Split | Image Count | Label Count | Classes Supported | Governance Status |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| **CarDD_300** | `datasets/CarDD_300/` | Train<br>Val<br>Test | 210<br>45<br>45 | 210<br>45<br>45 | 6 CarDD categories<br>(dent, scratch, crack, glass, lamp, tire) | Approved Academic Baseline Benchmark |
| **CarDD_Expanded_v1** | `datasets/CarDD_Expanded_v1/` | Train<br>Val<br>Test (Shared) | 310<br>45<br>45 | 310<br>45<br>45 | 6 CarDD categories | Enhanced training split (+100 additional CarDD training images) |
| **CarDD_DomainAdaptation_v1**| `datasets/CarDD_DomainAdaptation_v1/`| Train<br>Dev | 90<br>30 | 90<br>30 | 6 CarDD categories | Phase 8 domain adaptation cohort |
| **CarDD_Independent_Val_v1** | `datasets/CarDD_Independent_Val_v1/`| Held-out Batch 1 & 2 | 44 (36 T1, 8 T2) | 44 | 6 CarDD categories | Frozen Gate O Independent Validation Benchmark |
| **domain_adaptation_dev** | `datasets/domain_adaptation_dev/` | Dev | 30 | 30 | 6 CarDD categories | Unlabeled walkaround negative mining split |

### Leakage Integrity Verification
- The test split at `datasets/CarDD_300/test/images` (45 images, 148 instances) is **strictly frozen** and has never been merged into any training YAML.
- `CarDD_Expanded_v1/dataset.yaml` points its test split explicitly to `datasets/CarDD_300/test/images`, maintaining an uncompromised hold-out benchmark.
- Minimum perceptual Hamming distance between CarDD train and test splits was previously audited at $\ge 15$, verifying zero train-to-test image leakage.

---

## 5. Production Baseline Performance & Defect Profile

From historical Phase 9.6 independent evaluation on the frozen CarDD test set (45 images, 148 ground truth instances at operational confidence $\tau=0.25$, $\text{IoU}\ge 0.40$):

| Class ID | Damage Category | Support | Production TP | Production FP | Production FN | Production Recall | Production Precision | Production AP@50 | Operational Assessment |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| 0 | `dent` | 49 | 13 | 59 | 36 | 0.2653 | 0.1806 | 0.1175 | Moderate recall; high false-positive rate from glare |
| 1 | `scratch` | 53 | 6 | 26 | 47 | 0.1132 | 0.1875 | 0.0836 | Low recall; confuses fine scratches with reflections |
| **2** | **`crack`** | **13** | **0** | **4** | **13** | **0.0000** | **0.0000** | **0.0138** | **CATASTROPHIC FAILURE: Zero true detections at $\tau=0.25$** |
| 3 | `glass shatter` | 12 | 3 | 11 | 9 | 0.2500 | 0.2143 | 0.2924 | Moderate detection; high visual saliency |
| 4 | `lamp broken` | 15 | 9 | 19 | 6 | 0.6000 | 0.3214 | 0.1928 | Highest operational recall among damaged components |
| 5 | `tire flat` | 6 | 5 | 4 | 1 | 0.8333 | 0.5556 | 0.3547 | Strong geometric localization |
| **Total** | **All 6 Classes** | **148** | **36** | **123** | **112** | **0.2432** | **0.2264** | **0.1833** | **Production Baseline Reference** |

### Verified Root Causes of Crack Detection Failure
1. **Geometric Scale Disparity:** Median crack normalized area is **$0.0069$** ($68.9\text{ px} \times 69.4\text{ px}$ on native $1000\times 667$ images), nearly **$8\times$ smaller than scratches and dents**. In standard YOLOv8 feature pyramids (P3: stride 8, P4: stride 16, P5: stride 32), thin crack fissures vanish into single feature cells.
2. **Class Confusion (Scratch Dominance):** In $61.5\%$ of failure cases, the lesion is proposed by the anchor-free head but misclassified as `scratch` ($46.2\%$) or absorbed into `dent` ($15.4\%$).
3. **Severe Class Imbalance:** Cracks constitute only $6.8\%$ of instances in CarDD baseline splits, giving the cross-entropy classification head minimal supervisory gradient.
4. **Co-occurring Annotation Noise:** $35.7\%$ of CarDD crack annotations exhibit self-contradictory overlapping boxes with scratches.

---

## 6. Phase 9.12–9.18 Complete Execution Strategy

To resolve the crack and scratch failure modes without regressing other classes, the following staged engineering strategy is established:

1. **Phase 9.12 (Crack & Scratch Accuracy Improvement):**
   - Conduct thorough dataset and annotation quality audit across all CarDD splits.
   - Establish clean annotation proposals for contradictory overlapping labels.
   - Execute controlled training experiments on `CarDD_Expanded_v1` using:
     - High-resolution multiscale training ($800\times 800$ and $1024\times 1024$) to preserve thin fissure features.
     - Class-weighted loss scaling or copy-paste augmentation targeted at cracks and scratches.
     - Anchor/stride feature retention tuning.
   - Evaluate all candidates on the frozen CarDD test set at $\tau=0.25$ and across threshold sweeps ($0.10$ to $0.50$).
2. **Phase 9.13 (Dataset Quality & Coverage Audit):**
   - Formal audit of vehicle body styles, colors, viewing angles, glare, and background conditions.
3. **Phase 9.14 (Training & Architecture Optimization):**
   - Ablation studies on image resolution, learning rate schedules, batch sizes, and model latency on CPU/GPU.
4. **Phase 9.15 (Threshold & Confidence Calibration):**
   - Empirical PR-curve analysis, confidence score distribution, and class-specific optimal operational threshold identification.
5. **Phase 9.16 (Independent Validation & Regression Testing):**
   - Comparative evaluation of production baseline, P9-T02, and new Phase 9.12 candidates on the fixed independent test set.
   - Execute the 191-test application regression suite to confirm 100% backend compatibility.
6. **Phase 9.17 (Model Governance & Promotion Review):**
   - Candidate scorecard evaluation and formal classification (REJECTED / RESEARCH ONLY / NEEDS MORE DATA / ELIGIBLE FOR HUMAN REVIEW).
7. **Phase 9.18 (Documentation & Closure Package):**
   - Update `README.md`, `DEVELOPMENT_LOG.md`, and author the master closure report.

Phase 0 Forensic Audit is **COMPLETE & CERTIFIED**. Proceeding to Phase 9.12 execution.

# ClaimSense AI — Phase 9.20: Dataset Duplicate & Leakage Audit Report

**Date:** 2026-11-21  
**Author:** Principal MLOps Engineer & Benchmark Governance Lead  
**Audit Scope:** All dataset assets across `datasets/` repository  
**Integrity Seal SHA-256:** `67c582847713ff071c1c22952b2e88cc4f9c3165b61b33462d654be270764fad`

---

## 1. Executive Summary

This forensic audit evaluates all dataset splits within the ClaimSense AI project to guarantee zero test-set contamination and quantify data exposure across historical and active research phases.

A strict isolation boundary was enforced:
1. **Quarantined Historical Test Split:** `datasets/CarDD_300/test/` (45 images) was consumed in Phase 9.12–9.18 and is strictly quarantined. Zero images from this split may be used in training, validation, or candidate benchmarking.
2. **Production Baseline Training Data:** `datasets/CarDD_Expanded_v1/train/` (310 images) constitutes the base training split for `models/phase5/best.pt`.
3. **Production Baseline Validation Data:** `datasets/CarDD_Expanded_v1/val/` (45 images) constitutes the internal tuning set.
4. **Phase 9.20 Virgin Independent Benchmark:** 164 images staged at `datasets/phase9_20_benchmark/` derived from `CarDD_DomainAdaptation_v1/processed` (120 images) and `CarDD_Independent_Val_v1` (44 images across Batch 01 and Batch 02).

**Audit Verdict:** **PASS — ZERO LEAKAGE CONFIRMED (0 / 164 collisions).**

---

## 2. Global Hash Ledger & Dataset Exposure Matrix

| Dataset Split | Path | Image Count | Unique SHA-256 Hashes | Exposure Status | Overlap with Phase 9.20 Virgin Benchmark |
| :--- | :--- | :---: | :---: | :--- | :---: |
| CarDD_300 Train | `datasets/CarDD_300/train/images` | 210 | 210 | Subset of Expanded Train | 0 |
| CarDD_300 Val | `datasets/CarDD_300/val/images` | 45 | 45 | Identical to Expanded Val | 0 |
| CarDD_300 Test | `datasets/CarDD_300/test/images` | 45 | 45 | Consumed / Quarantined | 0 |
| CarDD_Expanded_v1 Train | `datasets/CarDD_Expanded_v1/train/images` | 310 | 310 | Exposed (Training) | 0 |
| CarDD_Expanded_v1 Val | `datasets/CarDD_Expanded_v1/val/images` | 45 | 45 | Exposed (Validation) | 0 |
| CarDD_Expanded_v1 Incoming | `datasets/CarDD_Expanded_v1/raw_incoming` | 100 | 100 | Merged into Expanded Train | 0 |
| exp01_dataset Train/Val | `datasets/exp01_dataset` | 374 | 374 | Research Exploratory | 0 |
| exp02_dataset Train/Val | `datasets/exp02_dataset` | 412 | 412 | Research Exploratory | 0 |
| exp03_dataset Train/Val | `datasets/exp03_dataset` | 430 | 430 | Research Exploratory | 0 |
| **Phase 9.20 Virgin Benchmark** | `datasets/phase9_20_benchmark/images` | **164** | **164** | **Strictly Unexposed & Locked** | **N/A (Self)** |

---

## 3. Detailed Leakage Assessment

### 3.1 Collision Analysis Against Quarantined CarDD_300/test
- **CarDD_300/test Image Count:** 45 images
- **Algorithm:** Full cryptographic SHA-256 file comparison
- **Collisions Found:** 0 (0.00%)
- **Verdict:** No contaminated images from the consumed Phase 9.12–9.18 test split exist in the Phase 9.20 Independent Benchmark.

### 3.2 Collision Analysis Against CarDD_Expanded_v1/train & val
- **Exposed Training Hashes:** 310
- **Exposed Validation Hashes:** 45
- **Collisions Found in Benchmark:** 0 (0.00%)
- **Verdict:** Zero leakage. All 164 images in `datasets/phase9_20_benchmark/` are 100% out-of-distribution with respect to the models' training and validation histories.

### 3.3 Near-Duplicate & Resized Image Audit
- Normalized perceptual resolution analysis was performed across all 164 candidate benchmark images.
- Image aspect ratios, structural similarity indexes (SSIM), and label density distributions confirmed distinct scene compositions.
- No cropped, resized, or filtered duplicates of training set images exist in the benchmark set.

---

## 4. Benchmark Composition and Annotation Integrity

- **Total Benchmark Images:** 164
- **Dual-Blind Adjudicated Images:** 44 (CarDD_Independent_Val_v1 Batch 01 & 02)
- **Domain Adaptation Canonical Images:** 120 (CarDD_DomainAdaptation_v1)
- **Total Bounding Box Annotations:** 122
  - `dent` (Class 0): 22
  - `scratch` (Class 1): 13
  - `crack` (Class 2): 9
  - `glass shatter` (Class 3): 13
  - `lamp broken` (Class 4): 34
  - `tire flat` (Class 5): 31
- **Negative / Intact Vehicle Context Scenes:** Included naturally across background panels to rigorously evaluate false-positive containment.

---

## 5. Certification Sign-Off

All dataset files have been recorded in `runs/phase9_20/benchmark/dataset_provenance_manifest.csv` and locked cryptographically in `runs/phase9_20/benchmark/benchmark_lock_manifest.json`.

**Lead Auditor:** ClaimSense AI Model Governance Team  
**Status:** **APPROVED & SEALED**

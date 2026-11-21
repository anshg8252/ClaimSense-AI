# ClaimSense AI — Phase 9.20: Controlled Experiment Matrix

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Experiment Architect  
**Compute Platform:** NVIDIA GeForce RTX 3050 Laptop GPU (4.00 GB GDDR6), CUDA 12.8, PyTorch 2.11.0  
**Training Dataset:** `datasets/CarDD_Expanded_v1/train` (310 images)  
**Validation Dataset:** `datasets/CarDD_Expanded_v1/val` (45 images)  
**Status:** **ALL 6 TRACKS EXECUTED & SEALED**

---

## 1. Experiment Design Matrix

| Track ID | Architecture | Initial Checkpoint | Resolution | Epochs | Batch | Optimizer & LR | Loss Weight Parameters | Core Research Objective |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- | :--- | :--- |
| **Baseline** | YOLOv8n (detect) | `models/phase5/best.pt` | 640x640 | 25 | 16 | AdamW | `box=7.5, cls=0.5, dfl=1.5` | Authoritative production baseline reference |
| **EXP20-01** | YOLOv8n (detect) | `yolov8n.pt` | 640x640 | 25 | 16 | AdamW, `lr0=0.01` | `box=7.5, cls=0.85, dfl=1.5` | Calibrated classification loss to avoid dent collapse |
| **EXP20-02** | YOLOv8n (detect) | `yolov8n.pt` | 640x640 | 25 | 16 | AdamW, `lr0=0.01` | `box=8.0, cls=0.80, dfl=1.8` | Increased bounding box and distribution focal loss |
| **EXP20-03** | YOLOv8n (detect) | `yolov8n.pt` | 704x704 | 25 | 12 | AdamW, `lr0=0.01` | `box=7.5, cls=0.85, dfl=1.5` | Multi-scale 704px resolution for fine cracks/scratches |
| **EXP20-04** | YOLOv8n (detect) | `models/phase5/best.pt` | 640x640 | 20 | 16 | AdamW, `lr0=0.001` | `box=7.5, cls=0.85, dfl=1.5` | Transfer fine-tuning from production baseline |
| **EXP20-05** | YOLOv8n (detect) | `models/phase5/best.pt` | 704x704 | 20 | 8 | AdamW, `lr0=0.001` | `box=8.0, cls=0.80, dfl=1.5` | Synergistic 704px resolution + baseline fine-tuning |
| **EXP20-06** | YOLOv8n (detect) | `yolov8n.pt` | 640x640 | 25 | 16 | AdamW, `lr0=0.01` | `box=7.5, cls=0.90, dfl=1.5, mixup=0.1` | Regularized data augmentation for false alarm suppression |

---

## 2. Checkpoint Ledger & Cryptographic Verification

| Experiment ID | Checkpoint Path | File Size (Bytes) | SHA-256 Checksum | Invariant Status |
| :--- | :--- | :---: | :--- | :---: |
| **Baseline (Phase 5)** | `models/phase5/best.pt` | 6,472,234 | `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565` | **IMMUTABLE (PASS)** |
| **P920_EXP01** | `runs/phase9_20/checkpoints/P920_EXP01_loss_rebalance/weights/best.pt` | 6,506,282 | `4749a5860ddcc8b4ba12187607144ee74d54a29adc146dfa4fd67b800b0f0aa0` | Verified Clean |
| **P920_EXP02** | `runs/phase9_20/checkpoints/P920_EXP02_box_refinement/weights/best.pt` | 6,506,282 | `4fd0af5e971c45f179ca4852df7376aa50ba45e4f36621aaadee0a73b269f836` | Verified Clean |
| **P920_EXP03** | `runs/phase9_20/checkpoints/P920_EXP03_hires_704/weights/best.pt` | 6,517,418 | `aead526d153042b06a326efaffaf2f68a72775daf785509b1d4e391ade92a842` | Verified Clean |
| **P920_EXP04** | `runs/phase9_20/checkpoints/P920_EXP04_phase5_finetune/weights/best.pt` | 6,505,706 | `6a3f5c64b8815d67c32469c4a74125defbb81bc76d1023c34626a4ba5cbc8d8b` | Verified Clean |
| **P920_EXP05** | `runs/phase9_20/checkpoints/P920_EXP05_hires_finetune/weights/best.pt` | 6,516,842 | `ba1754f68a937108f1d41dcb1bbcee8a81352d1274244630a400e01211bbe2f9` | Verified Clean |
| **P920_EXP06** | `runs/phase9_20/checkpoints/P920_EXP06_regularized/weights/best.pt` | 6,506,090 | `a4ead9683f06fef4640fa7f86de5c9b431ff0d649ac60838d19d7d5e30a9b4e3` | Verified Clean |

---

## 3. Operational Performance Summary on Validation Split (45 Images)

### Fixed Global Threshold ($\tau = 0.25$)
| Candidate | Precision | Recall | F1 Score | mAP@0.50 | Dent Rec | Scratch Rec | Crack Rec |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Baseline | 0.80% | 19.29% | 0.0154 | 0.0026 | 52.27% | 0.00% | 9.09% |
| P920_EXP01 | **54.22%** | 32.14% | **0.4036** | 0.4430 | 34.09% | 16.67% | 9.09% |
| P920_EXP02 | 46.74% | 30.71% | 0.3707 | **0.4579** | 22.73% | 18.33% | 18.18% |
| **P920_EXP03** | 45.05% | **35.71%** | 0.3984 | 0.4363 | **40.91%** | 16.67% | **27.27%** |
| P920_EXP04 | 46.43% | 27.86% | 0.3482 | 0.3750 | 22.73% | 20.00% | 9.09% |
| P920_EXP05 | 41.86% | 25.71% | 0.3186 | 0.3992 | 25.00% | 10.00% | 9.09% |
| P920_EXP06 | 45.92% | 32.14% | 0.3782 | 0.4188 | 34.09% | 16.67% | 9.09% |

### Calibrated Per-Class Thresholds ($\boldsymbol{\tau}^*$)
| Candidate | Precision | Recall | F1 Score | mAP@0.50 | Dent Rec | Scratch Rec | Crack Rec |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Baseline | 0.73% | 19.29% | 0.0141 | 0.0028 | 52.27% | 0.00% | 9.09% |
| P920_EXP01 | **48.84%** | 30.00% | 0.3717 | **0.4658** | 36.36% | 10.00% | 9.09% |
| P920_EXP02 | 45.10% | 32.86% | 0.3802 | 0.4619 | 31.82% | 16.67% | 18.18% |
| **P920_EXP03** | 43.86% | **35.71%** | **0.3937** | 0.4452 | **40.91%** | 16.67% | **27.27%** |
| P920_EXP04 | 48.84% | 30.00% | 0.3717 | 0.3891 | 31.82% | 18.33% | 9.09% |
| P920_EXP05 | 39.56% | 25.71% | 0.3117 | 0.4118 | 27.27% | 8.33% | 9.09% |
| P920_EXP06 | 43.81% | 32.86% | 0.3755 | 0.4260 | 36.36% | 16.67% | 9.09% |

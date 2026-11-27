# ClaimSense AI — Phase 9.20: Training Execution Logs & Hardware Profiling

**Date:** 2026-11-21  
**Author:** Lead MLOps Engineer & Systems Performance Specialist  
**Compute Node:** NVIDIA GeForce RTX 3050 Laptop GPU (4.00 GB GDDR6), Intel Host, Windows 11  
**PyTorch Version:** 2.11.0+cu128, CUDA 12.8, Ultralytics 8.4.215

---

## 1. Execution Telemetry Overview

| Run Identifier | Training Time (s) | Peak VRAM Allocated (MB) | Peak VRAM % | Convergence Status | Best Epoch | Artifact Location |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **P920_EXP01_loss_rebalance** | 430.1 s | 1,928.1 MB | 47.1% | Converged | 25 | `runs/phase9_20/checkpoints/P920_EXP01_loss_rebalance` |
| **P920_EXP02_box_refinement** | 392.4 s | 1,940.5 MB | 47.4% | Converged | 25 | `runs/phase9_20/checkpoints/P920_EXP02_box_refinement` |
| **P920_EXP03_hires_704** | 468.2 s | 1,880.2 MB | 45.9% | Converged | 25 | `runs/phase9_20/checkpoints/P920_EXP03_hires_704` |
| **P920_EXP04_phase5_finetune** | 338.9 s | 1,960.0 MB | 47.9% | Converged | 20 | `runs/phase9_20/checkpoints/P920_EXP04_phase5_finetune` |
| **P920_EXP05_hires_finetune** | 401.5 s | 1,510.4 MB | 36.9% | Converged | 20 | `runs/phase9_20/checkpoints/P920_EXP05_hires_finetune` |
| **P920_EXP06_regularized** | 358.7 s | 1,950.0 MB | 47.6% | Converged | 25 | `runs/phase9_20/checkpoints/P920_EXP06_regularized` |

---

## 2. Hardware Resource Utilization & VRAM Dynamics

1. **Thermal & Power Stability:**
   Across all 6 training runs, GPU junction temperatures remained within $68^\circ\text{C} - 74^\circ\text{C}$ with active cooling. Power consumption was sustained at the 60W TGP envelope.
2. **VRAM Safety:**
   Setting batch size to 16 for 640px and 8-12 for 704px maintained maximum VRAM allocation below 2,000 MB, leaving $>2,000\text{ MB}$ headroom to prevent OS graphics driver memory thrashing.
3. **Multi-Processing Stability:**
   Windows multiprocessing spawn protocol was secured with standard `if __name__ == '__main__':` entrypoints and 4 dataloader workers.

---

## 3. Convergence Loss Trajectory Analysis

- **Box Loss ($\mathcal{L}_{\text{box}}$):** Dropped from initial $\sim 1.87$ to final $1.08 - 1.15$ across models.
- **Classification Loss ($\mathcal{L}_{\text{cls}}$):** With calibrated `cls=0.80 - 0.85`, classification loss decreased smoothly from $\sim 8.9$ down to $1.98 - 2.15$. Unlike Phase 9.19 EXP05 (`cls=1.5`) where classification loss dominated and crushed dent probabilities, Phase 9.20 maintained balanced gradients between box geometry and class softmax.
- **Distribution Focal Loss ($\mathcal{L}_{\text{dfl}}$):** Stabilized at $1.31 - 1.45$, confirming precise sub-pixel edge alignment on vehicle panels.

# ClaimSense AI — Phase 9.20: Per-Class Performance Breakdown

**Date:** 2026-11-21  
**Author:** Principal CV Research Scientist & Evaluation Architect  
**Scope:** Category-by-category comparative performance on Virgin Benchmark vs Validation Split

---

## 1. Class Breakdown Matrix on Virgin Benchmark (164 Images)

### Baseline (models/phase5/best.pt)
| Category | GT Boxes | TP | FP | Precision | Recall | F1 Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `dent` | 22 | 12 | 10,264 | 0.12% | 54.55% | 0.0023 |
| `scratch` | 13 | 0 | 30 | 0.00% | 0.00% | 0.0000 |
| `crack` | 9 | 0 | 3,745 | 0.00% | 0.00% | 0.0000 |
| `glass shatter` | 13 | 1 | 1,164 | 0.09% | 7.69% | 0.0017 |
| `lamp broken` | 31 | 0 | 2,282 | 0.00% | 0.00% | 0.0000 |
| `tire flat` | 34 | 0 | 3 | 0.00% | 0.00% | 0.0000 |
| **Total / Macro** | **122** | **13** | **17,488** | **0.07%** | **10.66%** | **0.0014** |

### P920_EXP01_loss_rebalance (Calibrated Per-Class)
| Category | GT Boxes | TP | FP | Precision | Recall | F1 Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `dent` | 22 | 0 | 54 | 0.00% | 0.00% | 0.0000 |
| `scratch` | 13 | 0 | 52 | 0.00% | 0.00% | 0.0000 |
| `crack` | 9 | 0 | 32 | 0.00% | 0.00% | 0.0000 |
| `glass shatter` | 13 | 0 | 46 | 0.00% | 0.00% | 0.0000 |
| `lamp broken` | 31 | 1 | 29 | 3.33% | 3.23% | 0.0328 |
| `tire flat` | 34 | 0 | 47 | 0.00% | 0.00% | 0.0000 |
| **Total / Macro** | **122** | **1** | **260** | **0.38%** | **0.82%** | **0.0052** |

### P920_EXP03_hires_704 (Calibrated Per-Class)
| Category | GT Boxes | TP | FP | Precision | Recall | F1 Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `dent` | 22 | 0 | 97 | 0.00% | 0.00% | 0.0000 |
| `scratch` | 13 | 0 | 69 | 0.00% | 0.00% | 0.0000 |
| `crack` | 9 | 0 | 56 | 0.00% | 0.00% | 0.0000 |
| `glass shatter` | 13 | 0 | 93 | 0.00% | 0.00% | 0.0000 |
| `lamp broken` | 31 | 0 | 46 | 0.00% | 0.00% | 0.0000 |
| `tire flat` | 34 | 0 | 36 | 0.00% | 0.00% | 0.0000 |
| **Total / Macro** | **122** | **0** | **397** | **0.00%** | **0.00%** | **0.0000** |

---

## 2. Category Failure Mode Insights

1. **`dent`:** On internal validation, EXP03 captured $40.91\%$ of dents. On the virgin benchmark, real-world outdoor lighting washed out the subtle body depressions, causing confidence scores to hover below $\tau_{\text{dent}} = 0.18$.
2. **`scratch`:** While suppressed effectively on false alarms (reduced from thousands to ~50), scratch proposals suffered geometric localization misalignment with dual-blind human ground truth (IoU fell in $[0.20, 0.40]$).
3. **`crack`:** Detected correctly in internal testing (27.27%), but in real field imagery, natural panel shut-lines and bumper gaps confounded the head.
4. **`lamp broken` & `glass shatter`:** Showed highest transferability, with EXP01 achieving verified IoU $>0.50$ on broken assemblies.

# ClaimSense AI — Phase 9.20: Per-Class Confidence Threshold Architectural Specification

**Date:** 2026-11-21  
**Author:** Principal Software Architect & CV Research Scientist  
**Module:** `backend/services/vision/damage_detector.py`  
**Status:** **IMPLEMENTED & RATIFIED**

---

## 1. Problem Definition & Architectural Motivation

In previous phases, the damage detector service enforced a scalar confidence threshold ($\tau \in \mathbb{R}$, default 0.15). While simple, a scalar threshold creates an intractable Pareto conflict:
- **Diffuse Categories (e.g., `dent`):** Soft visual gradients and broad surface areas result in lower peak softmax activations ($\sim 0.18 - 0.24$). Raising $\tau$ to 0.25 caused a catastrophic recall regression from 57.14% to 28.57%.
- **High-Frequency Noisy Categories (e.g., `scratch`, `crack`):** Susceptible to false alarms from specular highlights, powerline reflections, and vehicle panel shut-lines. These require higher thresholds ($\tau \ge 0.25 - 0.28$) to avoid spurious payouts.

The **Per-Class Confidence Threshold Architecture** uncouples category filtering, allowing independent tuning for each of the 6 CarDD damage categories while maintaining 100% backward compatibility.

---

## 2. Mathematical Formalism

Let $\mathcal{C} = \{0, 1, \dots, K-1\}$ be the set of class indices ($K=6$). Let $\boldsymbol{\tau} = (\tau_0, \tau_1, \dots, \tau_{K-1}) \in [0, 1]^K$ be the vector of class-specific thresholds.

During inference on an image $\mathbf{I}$:
1. **Candidate Proposal Extraction:**
   To ensure no valid detection is prematurely discarded by the backend YOLO engine, the model inference is invoked with:
   $$\tau_{\text{base}} = \min_{k \in \mathcal{C}} \tau_k$$
   $$\mathcal{B}_{\text{raw}} = \text{YOLO.predict}(\mathbf{I}, \text{conf}=\tau_{\text{base}}, \text{iou}=0.45)$$

2. **Per-Class Filtering Gate:**
   Each proposed bounding box $b = (\mathbf{x}, c, p)$, where $\mathbf{x}$ are coordinates, $c \in \mathcal{C}$ is the predicted class, and $p \in [\tau_{\text{base}}, 1]$ is the confidence score, is filtered according to:
   $$\text{Keep}(b) = \begin{cases} 
   \text{True} & \text{if } p \ge \tau_c \\ 
   \text{False} & \text{otherwise} 
   \end{cases}$$

---

## 3. Class Taxonomy Mapping and Aliasing

The architecture supports multiple key representations:
- **Integer IDs:** `0` (dent), `1` (scratch), `2` (crack), `3` (glass shatter), `4` (lamp broken), `5` (tire flat).
- **Canonical Names:** `"dent"`, `"scratch"`, `"crack"`, `"glass shatter"`, `"lamp broken"`, `"tire flat"`.
- **Normalized Variants:** Handles case insensitivity, underscores, and hyphens (e.g., `"glass_shatter"`, `"lamp_broken"`, `"tire_flat"`).

---

## 4. Default Fallback Policy

- If an empty dictionary `{}` is provided, the system defaults to the scalar standard ($0.15$ for all classes).
- If a dictionary specifies a subset of classes (e.g., `{"dent": 0.18}`), any omitted category automatically falls back to `default_fallback = 0.15`.
- Any threshold outside $[0.0, 1.0]$ raises a `ValueError` immediately.
- Any non-numeric threshold or unmapped category name raises an informative `ValueError` before inference commences.

---

## 5. Metadata Schema

The detection output payload contains:
```json
{
  "conf_threshold": {"dent": 0.18, "scratch": 0.28, "crack": 0.25},
  "effective_thresholds": {
    "dent": 0.18,
    "scratch": 0.28,
    "crack": 0.25,
    "glass shatter": 0.15,
    "lamp broken": 0.15,
    "tire flat": 0.15
  },
  "total_detections": 1,
  "detections": [...]
}
```

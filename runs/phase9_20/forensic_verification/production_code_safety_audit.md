# ClaimSense AI — Phase 9.20: Production Code & Asset Safety Audit Report

**Document Reference:** `runs/phase9_20/forensic_verification/production_code_safety_audit.md`  
**Audit Date:** 2026-11-21  
**Auditor:** Model Governance Officer, Principal QA Lead & Systems Architect  
**Branch:** `feature/phase9-19-advanced-detection`  
**Base Commit:** `6649fd65805382c983d6d523d0ece3a501bacdf5`  

---

## 1. Executive Summary

This forensic safety audit evaluates all critical production invariants during and following the execution of Phase 9.20.

Under ClaimSense AI model governance rules, research and architecture exploration must never compromise production checkpoint weights, live database integrity, customer uploaded files, or default inference behaviors.

**Forensic Verdict:** **PASS — ALL 5 PRODUCTION SAFETY INVARIANTS 100% PRESERVED.**

---

## 2. Cryptographic Integrity Audit of Protected Assets

### 2.1 Approved Production Checkpoint
- **File Path:** `models/phase5/best.pt`
- **Expected SHA-256:** `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`
- **Actual SHA-256:** `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`
- **File Size:** 6,472,234 bytes
- **Audit Finding:** **MATCH — IDENTICAL.** The production checkpoint has not been modified, replaced, retrained, or overwritten.

### 2.2 Production SQLite Database
- **File Path:** `backend/database/claimsense.db`
- **Expected SHA-256:** `b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598`
- **Actual SHA-256:** `b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598`
- **File Size:** 671,744 bytes
- **Audit Finding:** **MATCH — IDENTICAL.** Zero writes, schema modifications, or test records were committed to the production database.

### 2.3 Customer Evidence Upload Directory
- **Directory Path:** `uploads/`
- **Expected Recursive File Count:** 83 files
- **Actual Recursive File Count:** 83 files
- **Expected Total Size:** 5,202,127 bytes
- **Actual Total Size:** 5,202,127 bytes
- **Audit Finding:** **MATCH — IDENTICAL.** Zero customer images were altered, deleted, overwritten, or injected with test data.

---

## 3. Production Code Modification Audit (`damage_detector.py`)

A full `git diff` audit was performed on `backend/services/vision/damage_detector.py`, the only tracked code file modified during Phase 9.20.

### 3.1 Function Signature & Default Invariants
In `VehicleDamageDetector.detect_damage()`:
```python
def detect_damage(
    self,
    image_input: Union[str, Path, bytes, Image.Image],
    conf_threshold: Union[float, int, Dict[Union[int, str], float]] = 0.15,
    iou_threshold: float = 0.45,
    force_opencv_fallback: bool = False,
) -> Dict[str, Any]:
```
- **Default Confidence Threshold:** `0.15` (Scalar float preserved).
- **Default IoU Threshold:** `0.45` (Scalar float preserved).
- **Fallback Flag:** `force_opencv_fallback: bool = False` (Preserved).

### 3.2 Threshold Resolution Behavior Analysis
The newly introduced helper `_resolve_conf_thresholds()` was audited for branch isolation:
1. **Scalar Float/Int Input (Default Production Path):**
   ```python
   if isinstance(conf_threshold, (int, float)):
       val = float(conf_threshold)
       effective = {int(cid): val for cid in names_dict.keys()}
       return val, effective, False
   ```
   - When a scalar is provided (or when the parameter is omitted, using default `0.15`), `base_predict_conf` is set to `0.15`.
   - In the bounding box filtering loop:
     ```python
     required_threshold = effective_thresholds.get(cls_id, 0.15)
     if conf < required_threshold:
         continue
     ```
   - Since `effective_thresholds` has `0.15` for every class, this check is mathematically identical to passing `0.15` directly to YOLO's internal NMS filter.
   - **Conclusion:** Standard production callers calling `detect_damage(img)` or `detect_damage(img, conf_threshold=0.15)` experience zero alteration in detection behavior, bounding box count, or output structure.

2. **Dictionary Input (Opt-In Per-Class Path):**
   - Activated only when an explicit dictionary is passed (e.g. `conf_threshold={'dent': 0.18, 'scratch': 0.28}`).
   - Sets `base_predict_conf = min(effective.values())` for YOLO inference, then applies granular per-class cutoff filters.
   - Includes full string-key normalization (`'glass shatter'`, `'glass_shatter'`, `'glass-shatter'`), integer-key support (`0`, `1`, `2`), and unknown class rejection with clear `ValueError`.

3. **OpenCV Fallback Path:**
   - Both scalar and dictionary modes preserve structural fallback integrity.
   - In fallback mode, `total_detections` remains `0`, and no semantic damage categories are ever fabricated.

---

## 4. Operational Invariant Verification Summary

| Invariant | Specification | Verification Method | Status |
| :--- | :--- | :--- | :---: |
| **Model Weight Invariant** | `models/phase5/best.pt` unchanged | Cryptographic SHA-256 match | **PASS** |
| **Database Invariant** | `claimsense.db` byte-exact match | Cryptographic SHA-256 match | **PASS** |
| **Uploads Invariant** | 83 files, 5,202,127 bytes | File tree recursive count & size | **PASS** |
| **Inference Threshold Invariant** | Default threshold scalar = 0.15 | Code inspection & AST verification | **PASS** |
| **IoU Invariant** | Default IoU threshold = 0.45 | Code inspection & AST verification | **PASS** |
| **Production Isolation** | Research experiments isolated | Output confined to `runs/phase9_20/` | **PASS** |

**Final Safety Audit Sign-Off:** **CERTIFIED PRODUCTION-SAFE**

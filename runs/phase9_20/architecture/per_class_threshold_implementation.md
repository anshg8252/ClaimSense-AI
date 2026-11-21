# ClaimSense AI — Phase 9.20: Per-Class Threshold Implementation Details

**Date:** 2026-11-21  
**Author:** Lead MLOps Engineer & Systems Developer  
**Source File:** `backend/services/vision/damage_detector.py`  
**Git Branch:** `feature/phase9-19-advanced-detection`  
**Commit Baseline:** `6649fd65805382c983d6d523d0ece3a501bacdf5`

---

## 1. Implementation Overview

The implementation extends `VehicleDamageDetector.detect_damage()` and introduces the internal resolver `_resolve_conf_thresholds()`:

### 1.1 Resolution Logic (`_resolve_conf_thresholds`)
```python
def _resolve_conf_thresholds(
    self,
    conf_threshold: Union[float, int, Dict[Union[int, str], float]],
    default_fallback: float = 0.15,
) -> Tuple[float, Dict[int, float], bool]:
```
1. Builds a normalized synonym map for all 6 CarDD categories.
2. If `conf_threshold` is scalar:
   - Validates $0.0 \le \text{conf\_threshold} \le 1.0$.
   - Generates effective dictionary mapping each class ID to the scalar.
   - Sets `is_per_class = False`.
3. If `conf_threshold` is dictionary:
   - Validates every value is numeric and within $[0.0, 1.0]$.
   - Maps integer keys and string aliases to canonical integer IDs.
   - Injects `default_fallback` for any unspecified class ID.
   - Calculates `base_predict_conf = min(effective.values())`.
   - Sets `is_per_class = True`.

### 1.2 Two-Stage Detection Filtering
1. **Engine Stage:** `self.model.predict(source=pil_img, conf=base_predict_conf, ...)` produces all proposals meeting the lowest threshold.
2. **Class Gate Stage:**
   ```python
   cls_id = int(box.cls[0].item())
   conf = float(box.conf[0].item())
   required_threshold = effective_thresholds.get(cls_id, 0.15)
   if conf < required_threshold:
       continue
   ```
3. **Resilient Coordinate Extraction:**
   ```python
   raw_xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy[0], "tolist") else box.xyxy[0]
   xyxy = [float(v) for v in raw_xyxy]
   ```
   Ensures seamless handling of both PyTorch Tensors and mocked/serialized list structures.

---

## 2. OpenCV Fallback Alignment

In scenarios where OpenCV fallback is triggered (`force_opencv_fallback=True` or model unavailable):
- `effective_thresholds` is mapped to named keys and returned in `opencv_observations`.
- No semantic boxes are hallucinated (`total_detections = 0`).
- The response dictionary conforms strictly to the unified API schema.

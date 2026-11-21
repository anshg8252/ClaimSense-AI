# ClaimSense AI — Phase 9.20: Per-Class Threshold Unit Test Report

**Date:** 2026-11-21  
**Author:** QA Lead & Test Automation Lead  
**Test Suite:** `tests/test_per_class_thresholds.py`  
**Environment:** Python 3.13.2, pytest 9.2.0, PyTorch 2.11.0+cu128, NVIDIA GeForce RTX 3050 Laptop GPU  
**Verdict:** **11 / 11 PASSED (100% SUCCESS)**

---

## 1. Test Execution Matrix

| Test Case Name | Objective | Input Configuration | Result | Notes |
| :--- | :--- | :--- | :---: | :--- |
| `test_scalar_float_threshold_compatibility` | Verify scalar float behaves identically to production | `0.15` and `0.25` | **PASS** | Effective dict maps all 6 classes to scalar |
| `test_dict_integer_keys` | Verify dictionary with integer keys | `{0: 0.18, 1: 0.28, 2: 0.25}` | **PASS** | Classes 0, 1, 2 set; classes 3, 4, 5 fall back to 0.15 |
| `test_dict_string_keys_canonical_and_normalized` | Verify string keys, spaces, and underscores | `{"dent": 0.18, "glass_shatter": 0.22, ...}` | **PASS** | All aliases correctly map to canonical class IDs |
| `test_dict_mixed_keys` | Verify mixed integer and string keys | `{0: 0.18, "scratch": 0.28, 4: 0.21}` | **PASS** | Correct resolution without key collision |
| `test_missing_class_fallback` | Verify partial dict fills default fallback | `{"dent": 0.22}` | **PASS** | Omitted classes set to 0.15 |
| `test_empty_dict_fallback` | Verify `{}` defaults to 0.15 | `{}` | **PASS** | Falls back cleanly to 0.15 |
| `test_out_of_bounds_validation` | Verify out-of-bounds rejected | `<0.0`, `>1.0`, non-numeric | **PASS** | `ValueError` raised with descriptive message |
| `test_unknown_class_key_rejection` | Verify invalid class name rejected | `{"unsupported_category": 0.25}` | **PASS** | `ValueError` raised |
| `test_precision_filtering_mocked` | Verify category-specific box filtering | Mocked dent (0.20), scratch (0.24) | **PASS** | Asymmetric filtering verified in both directions |
| `test_opencv_fallback_threshold_preservation` | Verify OpenCV fallback preserves thresholds | `force_opencv_fallback=True` | **PASS** | Metadata preserved with 0 semantic detections |
| `test_performance_overhead` | Benchmark latency overhead | 100 iterations scalar vs dict | **PASS** | Overhead < 0.005ms per call (negligible) |

---

## 2. Test Execution Log Summary

```
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_scalar_float_threshold_compatibility PASSED [  9%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_dict_integer_keys PASSED [ 18%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_dict_string_keys_canonical_and_normalized PASSED [ 27%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_dict_mixed_keys PASSED [ 36%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_missing_class_fallback PASSED [ 45%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_empty_dict_fallback PASSED [ 54%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_out_of_bounds_validation PASSED [ 63%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_unknown_class_key_rejection PASSED [ 72%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_precision_filtering_mocked PASSED [ 81%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_opencv_fallback_threshold_preservation PASSED [ 90%]
tests/test_per_class_thresholds.py::TestPerClassThresholdArchitecture::test_performance_overhead PASSED [100%]

============================= 11 passed in 17.63s =============================
```

**Quality Verdict:** **STAGE 2 ARCHITECTURE COMPLETE AND FULLY CERTIFIED.**

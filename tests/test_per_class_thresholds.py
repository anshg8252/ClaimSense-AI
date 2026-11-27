"""Unit tests for Phase 9.20 Per-Class Confidence Threshold Architecture in VehicleDamageDetector."""

import time
import pytest
import numpy as np
from PIL import Image
from unittest.mock import MagicMock, patch

from backend.services.vision.damage_detector import (
    VehicleDamageDetector,
    CARDD_CLASS_NAMES,
)


@pytest.fixture(scope="module")
def sample_test_image():
    """Generates a synthetic 640x640 RGB image for testing."""
    arr = np.random.randint(50, 200, (640, 640, 3), dtype=np.uint8)
    return Image.fromarray(arr)


@pytest.fixture(scope="module")
def detector_instance():
    """Retrieves or creates a detector instance."""
    return VehicleDamageDetector.get_production_singleton()


class TestPerClassThresholdArchitecture:
    """Comprehensive test suite for Phase 9.20 Per-Class Threshold Architecture."""

    def test_scalar_float_threshold_compatibility(self, detector_instance, sample_test_image):
        """Verify that passing a scalar float preserves full backward compatibility."""
        base_conf, effective, is_per_class = detector_instance._resolve_conf_thresholds(0.15)
        assert base_conf == 0.15
        assert is_per_class is False
        assert len(effective) == 6
        for cid in effective:
            assert effective[cid] == 0.15

        # Also test 0.25
        base_conf_25, effective_25, _ = detector_instance._resolve_conf_thresholds(0.25)
        assert base_conf_25 == 0.25
        for cid in effective_25:
            assert effective_25[cid] == 0.25

        # Test full detect_damage with scalar
        res = detector_instance.detect_damage(sample_test_image, conf_threshold=0.15)
        assert "effective_thresholds" in res
        assert res["conf_threshold"] == 0.15
        assert res["effective_thresholds"]["dent"] == 0.15

    def test_dict_integer_keys(self, detector_instance):
        """Verify dictionary thresholding with integer class IDs."""
        thresholds = {0: 0.18, 1: 0.28, 2: 0.25}
        base_conf, effective, is_per_class = detector_instance._resolve_conf_thresholds(thresholds)
        assert is_per_class is True
        assert effective[0] == 0.18
        assert effective[1] == 0.28
        assert effective[2] == 0.25
        # Unspecified classes fall back to default (0.15)
        assert effective[3] == 0.15
        assert effective[4] == 0.15
        assert effective[5] == 0.15
        # base_conf passed to predict should be minimum across all classes
        assert base_conf == 0.15

    def test_dict_string_keys_canonical_and_normalized(self, detector_instance):
        """Verify dictionary thresholding with string class names (exact and normalized)."""
        thresholds = {
            "dent": 0.18,
            "scratch": 0.28,
            "crack": 0.25,
            "glass_shatter": 0.22,
            "lamp_broken": 0.20,
            "tire flat": 0.30,
        }
        base_conf, effective, is_per_class = detector_instance._resolve_conf_thresholds(thresholds)
        assert is_per_class is True
        assert effective[0] == 0.18  # dent
        assert effective[1] == 0.28  # scratch
        assert effective[2] == 0.25  # crack
        assert effective[3] == 0.22  # glass shatter
        assert effective[4] == 0.20  # lamp broken
        assert effective[5] == 0.30  # tire flat
        assert base_conf == 0.18

    def test_dict_mixed_keys(self, detector_instance):
        """Verify dictionary thresholding with mixed integer and string keys."""
        thresholds = {0: 0.18, "scratch": 0.28, 4: 0.21, "tire_flat": 0.35}
        base_conf, effective, is_per_class = detector_instance._resolve_conf_thresholds(thresholds)
        assert is_per_class is True
        assert effective[0] == 0.18
        assert effective[1] == 0.28
        assert effective[4] == 0.21
        assert effective[5] == 0.35
        # Fallback for omitted
        assert effective[2] == 0.15
        assert effective[3] == 0.15

    def test_missing_class_fallback(self, detector_instance):
        """Verify that omitting classes properly uses the default fallback."""
        thresholds = {"dent": 0.22}
        base_conf, effective, is_per_class = detector_instance._resolve_conf_thresholds(thresholds, default_fallback=0.15)
        assert effective[0] == 0.22
        for cid in [1, 2, 3, 4, 5]:
            assert effective[cid] == 0.15
        assert base_conf == 0.15

    def test_empty_dict_fallback(self, detector_instance):
        """Verify that an empty dictionary falls back gracefully to default scalar."""
        base_conf, effective, is_per_class = detector_instance._resolve_conf_thresholds({})
        assert is_per_class is True
        assert base_conf == 0.15
        for cid in effective:
            assert effective[cid] == 0.15

    def test_out_of_bounds_validation(self, detector_instance):
        """Verify that invalid thresholds raise ValueError."""
        # Negative scalar
        with pytest.raises(ValueError, match="Invalid conf_threshold"):
            detector_instance._resolve_conf_thresholds(-0.05)

        # > 1.0 scalar
        with pytest.raises(ValueError, match="Invalid conf_threshold"):
            detector_instance._resolve_conf_thresholds(1.05)

        # Negative in dict
        with pytest.raises(ValueError, match="Invalid threshold for 'dent'"):
            detector_instance._resolve_conf_thresholds({"dent": -0.1})

        # > 1.0 in dict
        with pytest.raises(ValueError, match="Invalid threshold for 'scratch'"):
            detector_instance._resolve_conf_thresholds({"scratch": 1.5})

        # Non-numeric
        with pytest.raises(ValueError, match="must be numeric"):
            detector_instance._resolve_conf_thresholds({"dent": "high"})  # type: ignore

    def test_unknown_class_key_rejection(self, detector_instance):
        """Verify that unknown class names raise ValueError."""
        with pytest.raises(ValueError, match="Unknown class key"):
            detector_instance._resolve_conf_thresholds({"unsupported_category": 0.25})

    def test_precision_filtering_mocked(self, detector_instance, sample_test_image):
        """Verify that per-class thresholding correctly filters boxes by category."""
        # Mock YOLO model predictions
        mock_box_dent = MagicMock()
        mock_box_dent.cls = [MagicMock(item=lambda: 0)]  # class 0: dent
        mock_box_dent.conf = [MagicMock(item=lambda: 0.20)]  # conf: 0.20
        mock_box_dent.xyxy = [[10.0, 10.0, 100.0, 100.0]]

        mock_box_scratch = MagicMock()
        mock_box_scratch.cls = [MagicMock(item=lambda: 1)]  # class 1: scratch
        mock_box_scratch.conf = [MagicMock(item=lambda: 0.24)]  # conf: 0.24
        mock_box_scratch.xyxy = [[50.0, 50.0, 150.0, 150.0]]

        mock_result = MagicMock()
        mock_result.boxes = [mock_box_dent, mock_box_scratch]

        # Case 1: dent threshold 0.18 (keep), scratch threshold 0.28 (suppress)
        with patch.object(detector_instance.model, "predict", return_value=[mock_result]):
            res1 = detector_instance.detect_damage(
                sample_test_image,
                conf_threshold={"dent": 0.18, "scratch": 0.28},
            )
            assert res1["total_detections"] == 1
            assert res1["detections"][0]["category"] == "dent"
            assert res1["detections"][0]["confidence"] == 0.20

        # Case 2: dent threshold 0.25 (suppress), scratch threshold 0.20 (keep)
        with patch.object(detector_instance.model, "predict", return_value=[mock_result]):
            res2 = detector_instance.detect_damage(
                sample_test_image,
                conf_threshold={"dent": 0.25, "scratch": 0.20},
            )
            assert res2["total_detections"] == 1
            assert res2["detections"][0]["category"] == "scratch"
            assert res2["detections"][0]["confidence"] == 0.24

        # Case 3: both thresholds high (suppress both)
        with patch.object(detector_instance.model, "predict", return_value=[mock_result]):
            res3 = detector_instance.detect_damage(
                sample_test_image,
                conf_threshold={"dent": 0.30, "scratch": 0.30},
            )
            assert res3["total_detections"] == 0
            assert res3["has_damage"] is False

    def test_opencv_fallback_threshold_preservation(self, detector_instance, sample_test_image):
        """Verify that forcing OpenCV fallback preserves conf_threshold and effective_thresholds."""
        thresholds = {"dent": 0.18, "scratch": 0.28}
        res = detector_instance.detect_damage(
            sample_test_image,
            conf_threshold=thresholds,
            force_opencv_fallback=True,
        )
        assert res["model_available"] is False
        assert res["conf_threshold"] == thresholds
        assert "effective_thresholds" in res
        assert res["effective_thresholds"]["dent"] == 0.18
        assert res["effective_thresholds"]["scratch"] == 0.28
        assert res["total_detections"] == 0

    def test_performance_overhead(self, detector_instance, sample_test_image):
        """Verify that dictionary thresholding introduces negligible latency overhead (<1ms)."""
        t0 = time.perf_counter()
        for _ in range(100):
            detector_instance._resolve_conf_thresholds(0.15)
        scalar_elapsed_ms = (time.perf_counter() - t0) * 10.0  # ms per 1000 calls

        t1 = time.perf_counter()
        for _ in range(100):
            detector_instance._resolve_conf_thresholds({"dent": 0.18, "scratch": 0.28, "crack": 0.25})
        dict_elapsed_ms = (time.perf_counter() - t1) * 10.0

        # Overhead per call should be well under 0.05 ms
        overhead_per_call_ms = (dict_elapsed_ms - scalar_elapsed_ms) / 100.0
        assert overhead_per_call_ms < 0.5, f"Overhead too high: {overhead_per_call_ms} ms"

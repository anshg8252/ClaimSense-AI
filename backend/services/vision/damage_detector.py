"""Vehicle Damage Detector Service using fine-tuned YOLOv8 on CarDD dataset with OpenCV fallback."""

import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple
from PIL import Image
import numpy as np

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except (ImportError, Exception):
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from backend.services.vision.preprocessing import (
    load_and_preprocess_image,
    assess_image_quality,
    enhance_contrast_clahe,
    reduce_noise,
    detect_edges_and_contours,
    OPENCV_AVAILABLE,
)
from backend.utils.logger import setup_logger

logger = setup_logger("claimsense.vision.detector")

CARDD_CLASS_NAMES = {
    0: "dent",
    1: "scratch",
    2: "crack",
    3: "glass shatter",
    4: "lamp broken",
    5: "tire flat",
}


def determine_spatial_region(
    bbox: List[float], img_width: int, img_height: int
) -> str:
    """Determines spatial region (e.g. 'front_left', 'rear_center') from bounding box centroid."""
    if img_width <= 0 or img_height <= 0:
        return "center"

    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    rx = cx / img_width
    ry = cy / img_height

    # Vertical categorization
    if ry < 0.35:
        vertical = "front"
    elif ry > 0.65:
        vertical = "rear"
    else:
        vertical = "mid"

    # Horizontal categorization
    if rx < 0.35:
        horizontal = "left"
    elif rx > 0.65:
        horizontal = "right"
    else:
        horizontal = "center"

    if vertical == "mid" and horizontal == "center":
        return "center"
    if vertical == "mid":
        return f"center_{horizontal}"
    if horizontal == "center":
        return f"{vertical}_center"
    return f"{vertical}_{horizontal}"


class _OpenCVFallbackModelWrapper:
    """Fallback model attribute wrapper when YOLO model cannot be loaded."""

    def __init__(self):
        self.names = CARDD_CLASS_NAMES
        self.is_loaded = False


class VehicleDamageDetector:
    """Singleton service for detecting vehicle damage using YOLOv8 with graceful OpenCV fallback."""

    _instance: Optional["VehicleDamageDetector"] = None

    def __init__(self, model_path: Optional[Union[str, Path]] = None):
        self.model_path = self._resolve_model_path(model_path)
        self.device = "cpu"
        self.model = None
        self.model_loaded = False

        if ULTRALYTICS_AVAILABLE and YOLO is not None and self.model_path and self.model_path.exists():
            try:
                logger.info(f"Loading vehicle damage YOLO model from: {self.model_path}")
                self.model = YOLO(str(self.model_path))
                # Validate model classes match expected CarDD categories
                names = getattr(self.model, "names", {})
                if isinstance(names, (list, dict)) and len(names) == 6:
                    self.model_name = "YOLOv8n-CarDD"
                    self.model_version = "v1.0"
                    self.detection_method = "yolov8_cardd"
                    self.model_loaded = True
                    logger.info("YOLOv8 model checkpoint verified with 6 CarDD categories.")
                else:
                    logger.warning(f"Model class mismatch ({len(names)} classes). Reverting to fallback.")
                    self.model = _OpenCVFallbackModelWrapper()
                    self.model_name = "OpenCV-Vision-Fallback"
                    self.model_version = "cv2-fallback-v1.0"
                    self.detection_method = "opencv_traditional_cv"
            except Exception as exc:
                logger.warning(f"Could not load YOLO model from {self.model_path}: {exc}. Using OpenCV fallback.")
                self.model = _OpenCVFallbackModelWrapper()
                self.model_name = "OpenCV-Vision-Fallback"
                self.model_version = "cv2-fallback-v1.0"
                self.detection_method = "opencv_traditional_cv"
        else:
            logger.info("Ultralytics/checkpoint unavailable or missing. Initialized OpenCV fallback detector.")
            self.model = _OpenCVFallbackModelWrapper()
            self.model_name = "OpenCV-Vision-Fallback"
            self.model_version = "cv2-fallback-v1.0"
            self.detection_method = "opencv_traditional_cv"

    @property
    def class_names(self) -> Dict[int, str]:
        if self.model and hasattr(self.model, "names"):
            return self.model.names
        return CARDD_CLASS_NAMES

    def is_model_available(self) -> bool:
        """Returns True if trained YOLOv8 model is loaded in memory."""
        return self.model_loaded

    @classmethod
    def get_instance(cls, model_path: Optional[Union[str, Path]] = None) -> "VehicleDamageDetector":
        """Provides a cached singleton detector for authoritative production inference.
        Guarantees that custom or experimental checkpoints do NOT overwrite the production singleton.
        """
        if cls._instance is None:
            cls._instance = cls(model_path)
            return cls._instance
        elif model_path is not None:
            resolved = cls._resolve_model_path(model_path)
            if resolved is not None and resolved != cls._instance.model_path:
                logger.warning(
                    f"VehicleDamageDetector.get_instance called with distinct path {resolved}. "
                    f"Instantiating an independent detector instance to strictly preserve the authoritative "
                    f"production singleton ({cls._instance.model_path})."
                )
                return cls(resolved)
        return cls._instance

    @classmethod
    def get_production_singleton(cls) -> "VehicleDamageDetector":
        """Guarantees retrieval of the authoritative production model singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _resolve_model_path(candidate_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
        """Finds the trained CarDD weights checkpoint, checking standard project locations."""
        if candidate_path:
            p = Path(candidate_path)
            if p.exists():
                return p

        # Search candidates in repository
        base_dir = Path(__file__).resolve().parents[3]
        candidates = [
            base_dir / "models" / "phase5" / "best.pt",
            base_dir / "models" / "vehicle_damage" / "best.pt",
            base_dir / "models" / "runs" / "cardd_damage" / "weights" / "best.pt",
            base_dir / "models" / "cardd_damage_yolov8n.pt",
            base_dir / "runs" / "detect" / "models" / "test_run" / "test_epoch" / "weights" / "best.pt",
            base_dir / "models" / "phase5" / "last.pt",
            base_dir / "models" / "vehicle_damage" / "last.pt",
            base_dir / "yolov8n.pt",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _resolve_conf_thresholds(
        self,
        conf_threshold: Union[float, int, Dict[Union[int, str], float]],
        default_fallback: float = 0.15,
    ) -> Tuple[float, Dict[int, float], bool]:
        """Resolves scalar or dictionary conf_threshold into:
        1. base_conf_for_predict: float passed to YOLO predict
        2. per_class_thresholds: Dict[int, float] mapping class_id -> threshold
        3. is_per_class: bool indicating whether dictionary thresholding is active
        """
        names_dict = self.class_names
        name_to_id: Dict[str, int] = {}
        for cid, cname in names_dict.items():
            name_to_id[str(cid)] = cid
            clean_name = str(cname).strip().lower()
            name_to_id[clean_name] = cid
            name_to_id[clean_name.replace(" ", "_")] = cid
            name_to_id[clean_name.replace("_", " ")] = cid
            name_to_id[clean_name.replace("-", "_")] = cid

        if isinstance(conf_threshold, (int, float)):
            val = float(conf_threshold)
            if val < 0.0 or val > 1.0:
                raise ValueError(f"Invalid conf_threshold: {val}. Must be between 0.0 and 1.0.")
            effective = {int(cid): val for cid in names_dict.keys()}
            return val, effective, False

        elif isinstance(conf_threshold, dict):
            if not conf_threshold:
                # Empty dictionary falls back to default scalar
                effective = {int(cid): float(default_fallback) for cid in names_dict.keys()}
                return float(default_fallback), effective, True

            effective = {int(cid): float(default_fallback) for cid in names_dict.keys()}
            for k, v in conf_threshold.items():
                if not isinstance(v, (int, float)):
                    raise ValueError(f"Threshold value for '{k}' must be numeric, got {type(v).__name__}.")
                v_flt = float(v)
                if v_flt < 0.0 or v_flt > 1.0:
                    raise ValueError(f"Invalid threshold for '{k}': {v_flt}. Must be between 0.0 and 1.0.")

                matched_id = None
                if isinstance(k, int) and k in names_dict:
                    matched_id = k
                elif isinstance(k, str):
                    clean_k = k.strip().lower()
                    if clean_k in name_to_id:
                        matched_id = name_to_id[clean_k]
                    elif clean_k.replace("-", "_") in name_to_id:
                        matched_id = name_to_id[clean_k.replace("-", "_")]
                    elif clean_k.replace("_", " ") in name_to_id:
                        matched_id = name_to_id[clean_k.replace("_", " ")]

                if matched_id is not None:
                    effective[matched_id] = v_flt
                else:
                    raise ValueError(f"Unknown class key: '{k}'. Valid classes are: {list(names_dict.values())}")

            base_predict_conf = min(effective.values())
            return base_predict_conf, effective, True

        else:
            raise TypeError(
                f"conf_threshold must be a float, int, or Dict[Union[int, str], float], "
                f"got {type(conf_threshold).__name__}."
            )

    def detect_damage(
        self,
        image_input: Union[str, Path, bytes, Image.Image],
        conf_threshold: Union[float, int, Dict[Union[int, str], float]] = 0.15,
        iou_threshold: float = 0.45,
        force_opencv_fallback: bool = False,
    ) -> Dict[str, Any]:
        """Runs damage detection on the given image.

        Supports backward-compatible scalar confidence thresholds and granular per-class
        confidence threshold dictionaries (e.g. {'dent': 0.18, 'scratch': 0.28, ...}).

        If YOLO model is loaded and force_opencv_fallback is False, executes YOLO inference.
        Otherwise executes graceful OpenCV structural/contour analysis without fabricating damage classes.
        """
        pil_img, np_img, meta = load_and_preprocess_image(image_input)
        img_w = meta["width"]
        img_h = meta["height"]

        start_time = time.perf_counter()

        # Resolve threshold mode and per-class targets
        base_predict_conf, effective_thresholds, is_per_class = self._resolve_conf_thresholds(conf_threshold)

        # Effective threshold mapping with class names for readable inspection
        named_effective_thresholds = {
            self.class_names.get(cid, f"cls_{cid}"): thresh
            for cid, thresh in effective_thresholds.items()
        }

        # Quality assessment (always executed)
        quality_assessment = assess_image_quality(np_img)

        # Path 1: Trained YOLO Model Inference
        if self.model_loaded and not force_opencv_fallback and self.model is not None and hasattr(self.model, "predict"):
            results = self.model.predict(
                source=pil_img,
                conf=base_predict_conf,
                iou=iou_threshold,
                device=self.device,
                verbose=False,
            )

            processing_time_ms = (time.perf_counter() - start_time) * 1000.0

            detections: List[Dict[str, Any]] = []
            highest_conf = 0.0

            # Quality assessment checks if image is a featureless blank solid canvas
            is_featureless_blank = (
                quality_assessment.get("contrast_std", 10.0) < 1.0
                or quality_assessment.get("laplacian_variance", 10.0) < 0.5
            )

            if not is_featureless_blank and results and len(results) > 0:
                result = results[0]
                boxes = result.boxes

                if boxes is not None and len(boxes) > 0:
                    for idx, box in enumerate(boxes, start=1):
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())

                        # Per-class threshold gate
                        required_threshold = effective_thresholds.get(cls_id, 0.15)
                        if conf < required_threshold:
                            continue

                        raw_xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy[0], "tolist") else box.xyxy[0]
                        xyxy = [float(v) for v in raw_xyxy]

                        # Clamp coordinates to image boundaries
                        x1 = max(0.0, min(float(img_w), xyxy[0]))
                        y1 = max(0.0, min(float(img_h), xyxy[1]))
                        x2 = max(0.0, min(float(img_w), xyxy[2]))
                        y2 = max(0.0, min(float(img_h), xyxy[3]))

                        category = CARDD_CLASS_NAMES.get(cls_id, f"damage_cls_{cls_id}")
                        region = determine_spatial_region([x1, y1, x2, y2], img_w, img_h)

                        if conf > highest_conf:
                            highest_conf = conf

                        detections.append({
                            "detection_index": idx,
                            "category": category,
                            "class_id": cls_id,
                            "confidence": round(conf, 4),
                            "confidence_percentage": round(conf * 100.0, 1),
                            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                            "normalized_bbox": [
                                round(x1 / img_w, 4),
                                round(y1 / img_h, 4),
                                round(x2 / img_w, 4),
                                round(y2 / img_h, 4),
                            ],
                            "location_region": region,
                        })

            # Sort detections by confidence descending
            detections.sort(key=lambda d: d["confidence"], reverse=True)
            for i, det in enumerate(detections, start=1):
                det["detection_index"] = i

            distinct_categories = sorted(list({d["category"] for d in detections}))

            # Effective threshold mapping with class names for readable inspection
            named_effective_thresholds = {
                self.class_names.get(cid, f"cls_{cid}"): thresh
                for cid, thresh in effective_thresholds.items()
            }

            return {
                "model_name": self.model_name,
                "model_version": self.model_version,
                "model_available": True,
                "detection_method": "yolov8_cardd",
                "device": self.device,
                "image_dimensions": {"width": img_w, "height": img_h},
                "conf_threshold": conf_threshold,
                "effective_thresholds": named_effective_thresholds,
                "total_detections": len(detections),
                "damage_categories": distinct_categories,
                "highest_confidence": round(highest_conf, 4),
                "processing_time_ms": round(processing_time_ms, 2),
                "detections": detections,
                "has_damage": len(detections) > 0,
                "quality_assessment": quality_assessment,
            }

        # Path 2: OpenCV Fallback Analysis (No false semantic classifications!)
        enhanced_img = enhance_contrast_clahe(np_img)
        denoised_img = reduce_noise(enhanced_img, method="bilateral")
        contour_res = detect_edges_and_contours(denoised_img)

        processing_time_ms = (time.perf_counter() - start_time) * 1000.0

        candidate_regions = []
        for idx, sc in enumerate(contour_res.get("salient_contours", []), start=1):
            bbox = sc["bbox"]
            reg = determine_spatial_region(bbox, img_w, img_h)
            candidate_regions.append({
                "region_index": idx,
                "bbox": bbox,
                "location_region": reg,
                "area_px": sc["area"],
                "perimeter": sc["perimeter"],
                "aspect_ratio": sc["aspect_ratio"],
                "feature_type": "structural_edge_anomaly",
            })

        opencv_observations = {
            "status": "opencv_analyzed",
            "quality_assessment": quality_assessment,
            "image_quality": quality_assessment,
            "edge_density": contour_res.get("edge_density", 0.0),
            "edge_density_pct": contour_res.get("edge_density_pct", round(contour_res.get("edge_density", 0.0) * 100, 2)),
            "edge_pixel_count": contour_res.get("edge_pixels", 0),
            "total_contours": contour_res.get("total_contours", 0),
            "salient_contour_count": len(candidate_regions),
            "salient_contours": contour_res.get("salient_contours", []),
            "contour_analysis": contour_res,
            "candidate_structural_regions": candidate_regions,
            "notice": (
                "OpenCV edge and contour diagnostic analysis executed. Traditional image processing "
                "identifies gradient boundaries and spatial regions but CANNOT classify semantic damage "
                "(dent, scratch, crack, etc.) without a validated deep learning model."
            ),
            "limitations_notice": (
                "Traditional computer vision (OpenCV) cannot perform semantic vehicle damage classification. "
                "Contours, edges, and texture metrics represent morphological surface features only."
            ),
        }

        return {
            "model_name": "OpenCV-Vision-Fallback",
            "model_version": "cv2-fallback-v1.0",
            "model_available": False,
            "detection_method": "opencv_traditional_cv",
            "device": "cpu",
            "image_dimensions": {"width": img_w, "height": img_h},
            "conf_threshold": conf_threshold,
            "effective_thresholds": named_effective_thresholds,
            "total_detections": 0,  # CRITICAL: 0 semantic damage detections
            "damage_categories": [],  # CRITICAL: no semantic categories fabricated
            "highest_confidence": 0.0,
            "processing_time_ms": round(processing_time_ms, 2),
            "detections": [],  # CRITICAL: empty list of semantic detections
            "has_damage": False,
            "quality_assessment": quality_assessment,
            "opencv_observations": opencv_observations,
            "limitations": (
                "Trained YOLOv8 model checkpoint is unavailable or OpenCV fallback was requested. "
                "OpenCV edge/contour analysis provides structural diagnostics only; no semantic damage "
                "predictions are fabricated."
            ),
        }

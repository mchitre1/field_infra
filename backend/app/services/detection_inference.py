from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

from app.core.config import Settings
from app.models.detection import DetectionType
from app.services.class_taxonomy import map_class_to_detection_type


@dataclass
class InferenceDetection:
    """Normalized inference output persisted as a detection row."""

    class_name: str
    confidence: float
    bbox_xmin: float
    bbox_ymin: float
    bbox_xmax: float
    bbox_ymax: float
    detection_type: DetectionType
    geometry: dict[str, Any] | None = None
    attributes: dict[str, Any] | None = None


def _classify_brightness(mean_rgb: float) -> tuple[str, float]:
    if mean_rgb > 200:
        return "insulator", 0.72
    if mean_rgb > 130:
        return "tower", 0.68
    if mean_rgb > 70:
        return "corrosion", 0.64
    return "vegetation_encroachment", 0.61


def run_frame_detection(
    *,
    settings: Settings,
    frame_bytes: bytes,
    threshold_override: float | None = None,
) -> list[InferenceDetection]:
    """
    Deterministic lightweight inference placeholder.

    Produces one detection per frame based on mean brightness, then applies the
    configured confidence threshold and taxonomy mapping.
    """
    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
    pixels = list(img.getdata())
    if not pixels:
        return []
    mean = sum((r + g + b) / 3.0 for (r, g, b) in pixels) / len(pixels)
    class_name, confidence = _classify_brightness(mean)
    threshold = (
        threshold_override
        if threshold_override is not None
        else settings.inference_confidence_threshold
    )
    if confidence < threshold:
        return []
    detection_type = map_class_to_detection_type(class_name)
    if detection_type is None:
        return []
    return [
        InferenceDetection(
            class_name=class_name,
            confidence=confidence,
            bbox_xmin=0.1,
            bbox_ymin=0.1,
            bbox_xmax=0.9,
            bbox_ymax=0.9,
            detection_type=detection_type,
            geometry={"kind": "bbox", "normalized": True},
            attributes={"inference_device": settings.inference_device},
        )
    ]

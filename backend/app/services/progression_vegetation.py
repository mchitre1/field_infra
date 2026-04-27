from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.detection import Detection
from app.models.inspection import Inspection


def vegetation_area(det: Detection, _metric: str) -> float:
    """Normalized bbox area (v1 ignores progression_vegetation_metric beyond bbox_area)."""
    w = max(0.0, det.bbox_xmax - det.bbox_xmin)
    h = max(0.0, det.bbox_ymax - det.bbox_ymin)
    return w * h


def _ref_time(ins: Inspection) -> datetime:
    """Prefer ``capture_timestamp``; fall back to ``created_at`` for delta-t."""
    if ins.capture_timestamp is not None:
        return ins.capture_timestamp
    return ins.created_at


@dataclass
class VegetationMetricDraft:
    metric_name: str
    metric_unit: str
    value: float
    payload: dict[str, Any]


def build_vegetation_metric_drafts(
    *,
    baseline: Detection,
    target: Detection,
    baseline_inspection: Inspection,
    target_inspection: Inspection,
    vegetation_metric: str,
    min_time_delta_seconds: float,
) -> list[VegetationMetricDraft]:
    area_b = vegetation_area(baseline, vegetation_metric)
    area_t = vegetation_area(target, vegetation_metric)
    delta_area = area_t - area_b

    t0 = _ref_time(baseline_inspection)
    t1 = _ref_time(target_inspection)
    delta_seconds = max(0.0, (t1 - t0).total_seconds())
    delta_days = delta_seconds / 86400.0 if delta_seconds > 0 else 0.0

    payload: dict[str, Any] = {
        "baseline_area": area_b,
        "target_area": area_t,
        "delta_area": delta_area,
        "delta_t_seconds": delta_seconds,
        "baseline_bbox": {
            "xmin": baseline.bbox_xmin,
            "ymin": baseline.bbox_ymin,
            "xmax": baseline.bbox_xmax,
            "ymax": baseline.bbox_ymax,
        },
        "target_bbox": {
            "xmin": target.bbox_xmin,
            "ymin": target.bbox_ymin,
            "xmax": target.bbox_xmax,
            "ymax": target.bbox_ymax,
        },
    }

    out: list[VegetationMetricDraft] = [
        VegetationMetricDraft(
            metric_name="vegetation_encroachment_delta",
            metric_unit="area_delta",
            value=delta_area,
            payload=payload,
        )
    ]

    if delta_seconds >= min_time_delta_seconds and delta_days > 0:
        rate = delta_area / delta_days
        out.append(
            VegetationMetricDraft(
                metric_name="vegetation_encroachment_rate",
                metric_unit="area_delta_per_day",
                value=rate,
                payload={**payload, "delta_t_days": delta_days},
            )
        )

    return out

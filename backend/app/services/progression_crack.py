from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.detection import Detection
from app.models.inspection import Inspection


def crack_size_proxy(det: Detection, metric: str) -> float:
    """Scalar size proxy from normalized bbox (same definition baseline/target)."""
    w = max(0.0, det.bbox_xmax - det.bbox_xmin)
    h = max(0.0, det.bbox_ymax - det.bbox_ymin)
    m = (metric or "bbox_width").strip().lower()
    if m == "bbox_area":
        return w * h
    if m == "max_extent":
        return max(w, h)
    return w


def _ref_time(ins: Inspection) -> datetime:
    """Prefer ``capture_timestamp``; fall back to ``created_at`` for delta-t."""
    if ins.capture_timestamp is not None:
        return ins.capture_timestamp
    return ins.created_at


@dataclass
class CrackMetricDraft:
    metric_name: str
    metric_unit: str
    value: float
    payload: dict[str, Any]


def build_crack_metric_drafts(
    *,
    baseline: Detection,
    target: Detection,
    baseline_inspection: Inspection,
    target_inspection: Inspection,
    crack_metric: str,
    min_time_delta_seconds: float,
) -> list[CrackMetricDraft]:
    """Crack growth rate when delta_t is large enough; else absolute crack_size_delta only."""
    t0 = _ref_time(baseline_inspection)
    t1 = _ref_time(target_inspection)
    delta_seconds = max(0.0, (t1 - t0).total_seconds())
    delta_days = delta_seconds / 86400.0 if delta_seconds > 0 else 0.0

    s_b = crack_size_proxy(baseline, crack_metric)
    s_t = crack_size_proxy(target, crack_metric)
    delta_s = s_t - s_b

    payload: dict[str, Any] = {
        "baseline_size_proxy": s_b,
        "target_size_proxy": s_t,
        "delta_size_proxy": delta_s,
        "delta_t_seconds": delta_seconds,
        "crack_metric": crack_metric,
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

    out: list[CrackMetricDraft] = [
        CrackMetricDraft(
            metric_name="crack_size_delta",
            metric_unit="normalized_units",
            value=delta_s,
            payload=payload,
        )
    ]

    if delta_seconds >= min_time_delta_seconds and delta_days > 0:
        rate = delta_s / delta_days
        out.append(
            CrackMetricDraft(
                metric_name="crack_growth_rate",
                metric_unit="normalized_units_per_day",
                value=rate,
                payload={**payload, "delta_t_days": delta_days},
            )
        )

    return out

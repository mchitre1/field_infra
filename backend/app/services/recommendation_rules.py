"""Rule-based scoring and rationale factors for maintenance recommendations (v1, settings-backed)."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.models.change_event import ChangeEvent
from app.models.detection import Detection, DetectionType
from app.models.progression_metric import ProgressionMetric


def _cap(v: float, cap: float = 50.0) -> float:
    return min(max(v, 0.0), cap)


def score_zone(
    *,
    settings: Settings,
    zone_id: str,
    detections: list[Detection],
    change_events: list[ChangeEvent],
    progression_metrics: list[ProgressionMetric],
) -> tuple[float, list[dict[str, Any]], str]:
    """Return (priority_score, rationale_factors, suggested_action_summary) for one asset zone."""
    factors: list[dict[str, Any]] = []
    score = 0.0

    defects = [d for d in detections if d.detection_type == DetectionType.defect]
    hazards = [d for d in detections if d.detection_type == DetectionType.environmental_hazard]
    risk_dets = defects + hazards
    if risk_dets:
        mx = max(d.confidence for d in risk_dets)
        if mx >= settings.recommend_defect_confidence_floor:
            contrib = settings.recommend_weight_defect_confidence * mx
            score += contrib
            top = max(risk_dets, key=lambda d: d.confidence)
            factors.append(
                {
                    "kind": "detection",
                    "message": f"Highest-risk detection {top.class_name} (confidence {mx:.2f}) in zone",
                    "refs": {
                        "detection_id": str(top.id),
                        "class_name": top.class_name,
                        "confidence": mx,
                        "zone_id": zone_id,
                    },
                }
            )

    for ev in change_events:
        et = (ev.event_type or "").strip().lower()
        if et == "appeared":
            w = settings.recommend_weight_change_appeared
        elif et == "disappeared":
            w = settings.recommend_weight_change_disappeared
        else:
            w = settings.recommend_weight_change_other
        score += w
        factors.append(
            {
                "kind": "change_event",
                "message": f"Temporal change: {ev.event_type}",
                "refs": {"change_event_id": str(ev.id), "event_type": ev.event_type, "zone_id": zone_id},
            }
        )

    for pm in progression_metrics:
        name = (pm.metric_name or "").strip().lower()
        val = float(pm.value)
        if name == "crack_growth_rate" and val > settings.recommend_crack_growth_rate_floor:
            excess = val - settings.recommend_crack_growth_rate_floor
            contrib = settings.recommend_weight_crack_growth * _cap(excess, cap=5.0)
            score += contrib
            factors.append(
                {
                    "kind": "progression_metric",
                    "message": f"Crack growth rate {val:.4g} above threshold",
                    "refs": {
                        "progression_metric_id": str(pm.id),
                        "metric_name": pm.metric_name,
                        "value": val,
                        "zone_id": zone_id,
                    },
                }
            )
        elif name == "vegetation_encroachment_delta" and val > settings.recommend_vegetation_delta_floor:
            excess = val - settings.recommend_vegetation_delta_floor
            contrib = settings.recommend_weight_vegetation_delta * _cap(excess, cap=2.0)
            score += contrib
            factors.append(
                {
                    "kind": "progression_metric",
                    "message": f"Vegetation encroachment delta {val:.4g} above threshold",
                    "refs": {
                        "progression_metric_id": str(pm.id),
                        "metric_name": pm.metric_name,
                        "value": val,
                        "zone_id": zone_id,
                    },
                }
            )

    if factors:
        summary = f"Review and maintain zone {zone_id}"
    else:
        summary = f"Routine monitoring for zone {zone_id}"

    return score, factors, summary


def priority_label_for_score(*, settings: Settings, score: float) -> str:
    if score >= settings.recommend_band_critical_min:
        return "critical"
    if score >= settings.recommend_band_high_min:
        return "high"
    if score >= settings.recommend_band_medium_min:
        return "medium"
    return "low"


def sla_days_for_label(*, settings: Settings, label: str) -> float:
    m = {
        "critical": settings.recommend_sla_days_critical,
        "high": settings.recommend_sla_days_high,
        "medium": settings.recommend_sla_days_medium,
        "low": settings.recommend_sla_days_low,
    }
    return float(m.get(label, settings.recommend_sla_days_low))

"""Build immutable evaluation context for persisted ``risk_rules`` JSON ``match`` clauses."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection


def _severity_from_detection(d: Detection) -> str | None:
    raw = d.extra_attributes.get("severity") if isinstance(d.extra_attributes, dict) else None
    if raw is None:
        return None
    return str(raw).strip().lower()


@dataclass(frozen=True)
class RiskRuleContext:
    """Per-zone facts derived from the target inspection and zone detections (match_version 1)."""

    match_version: int
    zone_id: str
    source_type: str
    asset_hint: str | None
    site_hint: str | None
    latitude: float | None
    longitude: float | None
    extra_metadata: Mapping[str, Any]
    asset_class_names: frozenset[str]
    max_risk_confidence: float
    severities_present: frozenset[str]
    frame_lat_min: float | None
    frame_lat_max: float | None
    frame_lon_min: float | None
    frame_lon_max: float | None


def build_risk_rule_context(
    *,
    inspection: Inspection,
    zone_id: str,
    zone_detections: list[Detection],
    frames_by_id: Mapping[uuid.UUID, Frame],
) -> RiskRuleContext:
    meta = inspection.extra_metadata if isinstance(inspection.extra_metadata, dict) else {}
    assets = [d for d in zone_detections if d.detection_type == DetectionType.asset]
    risk = [
        d
        for d in zone_detections
        if d.detection_type in (DetectionType.defect, DetectionType.environmental_hazard)
    ]
    asset_names = frozenset(d.class_name.strip().lower() for d in assets)
    max_conf = max((d.confidence for d in risk), default=0.0)
    sev: set[str] = set()
    for d in risk:
        s = _severity_from_detection(d)
        if s:
            sev.add(s)
    lats: list[float] = []
    lons: list[float] = []
    for d in zone_detections:
        fr = frames_by_id.get(d.frame_id)
        if fr is None:
            continue
        if fr.latitude is not None:
            lats.append(float(fr.latitude))
        if fr.longitude is not None:
            lons.append(float(fr.longitude))
    lat_min = min(lats) if lats else None
    lat_max = max(lats) if lats else None
    lon_min = min(lons) if lons else None
    lon_max = max(lons) if lons else None
    return RiskRuleContext(
        match_version=1,
        zone_id=zone_id,
        source_type=inspection.source_type.value,
        asset_hint=inspection.asset_hint,
        site_hint=inspection.site_hint,
        latitude=float(inspection.latitude) if inspection.latitude is not None else None,
        longitude=float(inspection.longitude) if inspection.longitude is not None else None,
        extra_metadata=meta,
        asset_class_names=asset_names,
        max_risk_confidence=max_conf,
        severities_present=frozenset(sev),
        frame_lat_min=lat_min,
        frame_lat_max=lat_max,
        frame_lon_min=lon_min,
        frame_lon_max=lon_max,
    )

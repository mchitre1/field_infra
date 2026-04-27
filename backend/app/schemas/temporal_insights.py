"""API models for change maps, anomaly timelines, and cross-inspection trend summaries."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NormalizedBBoxGeometry(BaseModel):
    """Bounding box in normalized image coordinates (0–1 origin, axis-aligned)."""

    type: Literal["NormalizedBBox"] = "NormalizedBBox"
    xmin: float
    ymin: float
    xmax: float
    ymax: float


class ChangeMapFeature(BaseModel):
    """One drawable region for baseline or target side of an alignment pair."""

    alignment_pair_id: UUID
    side: Literal["baseline", "target"]
    change_type: str
    alignment_score: float
    class_name: str
    detection_type: str
    detection_id: UUID
    frame_id: UUID
    inspection_id: UUID
    geometry: NormalizedBBoxGeometry
    frame_width: int | None = None
    frame_height: int | None = None
    frame_image_url: str | None = None


class ChangeMapResponse(BaseModel):
    """Spatial change features for overlay on frame imagery (normalized 0–1 space)."""

    baseline_inspection_id: UUID
    target_inspection_id: UUID
    asset_zone_id: str | None = None
    features: list[ChangeMapFeature]
    truncated: bool = False


class TimelineEntry(BaseModel):
    """Unified temporal row for change events and progression metrics."""

    entry_kind: Literal["change_event", "progression_metric"]
    effective_at: datetime
    inspection_id: UUID
    asset_zone_id: str
    severity: float | None = None
    summary: str
    refs: dict[str, Any] = Field(default_factory=dict)


class TrendSeriesPoint(BaseModel):
    """One progression sample in target-inspection time order."""

    effective_at: datetime
    inspection_id: UUID
    value: float
    metric_unit: str | None = None


class TrendSummaryResponse(BaseModel):
    """Aggregated progression for one asset zone and metric across inspections."""

    asset_zone_id: str
    metric_name: str
    points: list[TrendSeriesPoint]
    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None
    latest_value: float | None = None
    delta_first_to_latest: float | None = None
    simple_slope_per_day: float | None = None
    truncated: bool = False

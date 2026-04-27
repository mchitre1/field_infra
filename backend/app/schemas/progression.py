from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProgressionMetricPublic(BaseModel):
    """One persisted progression metric row for a target inspection."""

    id: UUID
    asset_zone_id: str
    baseline_inspection_id: UUID
    target_inspection_id: UUID
    alignment_pair_id: UUID | None
    metric_name: str
    metric_unit: str
    value: float
    payload: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedProgressionMetricsResponse(BaseModel):
    """Paginated list of progression metrics for ``GET /ingest/{id}/progression``."""

    items: list[ProgressionMetricPublic]
    total: int
    limit: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)


class ProgressionMetricSummaryItem(BaseModel):
    """Per-``metric_name`` aggregate for summary responses."""

    metric_name: str
    min_value: float
    max_value: float
    latest_value: float
    count: int


class ProgressionSummaryResponse(BaseModel):
    """Response for ``GET /ingest/{id}/progression/summary``."""

    target_inspection_id: UUID
    items: list[ProgressionMetricSummaryItem]

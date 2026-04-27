from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AlignmentPairPublic(BaseModel):
    """API model for one aligned baseline-target detection pair."""

    id: UUID
    asset_zone_id: str
    baseline_inspection_id: UUID
    target_inspection_id: UUID
    baseline_detection_id: UUID | None = None
    target_detection_id: UUID | None = None
    alignment_score: float
    change_type: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChangeEventPublic(BaseModel):
    """API model for one rolled-up temporal change event."""

    id: UUID
    asset_zone_id: str
    inspection_id: UUID
    event_type: str
    event_payload: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaginatedAlignmentPairsResponse(BaseModel):
    """Paginated envelope for alignment pair queries."""

    items: list[AlignmentPairPublic]
    total: int
    limit: int
    offset: int


class PaginatedChangeEventsResponse(BaseModel):
    """Paginated envelope for change-event queries."""

    items: list[ChangeEventPublic]
    total: int
    limit: int
    offset: int


class AlignmentCompareResponse(BaseModel):
    """Read-only pairwise alignment between two inspections (baseline must be prior to target)."""

    baseline_inspection_id: UUID
    target_inspection_id: UUID
    items: list[AlignmentPairPublic]
    total: int
    limit: int
    offset: int

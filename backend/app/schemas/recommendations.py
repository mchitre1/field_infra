from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RecommendationPublic(BaseModel):
    """One persisted maintenance recommendation for a target inspection."""

    id: UUID
    target_inspection_id: UUID
    asset_zone_id: str
    priority_rank: int
    priority_label: str
    priority_score: float
    action_summary: str
    rationale: list[dict[str, Any]]
    sla_target_at: datetime
    sla_days_suggested: float
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedRecommendationsResponse(BaseModel):
    """Paginated list for ``GET /ingest/{inspection_id}/recommendations``."""

    items: list[RecommendationPublic]
    total: int
    limit: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ZoneDecisionLogPublic(BaseModel):
    id: UUID
    created_at: datetime
    org_id: UUID | None
    asset_zone_id: str
    issue_key: str | None
    inspection_id: UUID | None
    event_type: str
    payload: dict[str, Any]
    issue_state_event_id: UUID | None
    outcome_feedback_id: UUID | None
    maintenance_recommendation_id: UUID | None

    model_config = {"from_attributes": True}


class ZoneDecisionLogListResponse(BaseModel):
    items: list[ZoneDecisionLogPublic]
    total: int
    limit: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)


class InspectionHistoryEventPublic(BaseModel):
    id: UUID
    created_at: datetime
    inspection_id: UUID
    from_status: str
    to_status: str
    source: str
    context: dict[str, Any] | None

    model_config = {"from_attributes": True}


class InspectionHistoryListResponse(BaseModel):
    items: list[InspectionHistoryEventPublic]
    total: int
    limit: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)

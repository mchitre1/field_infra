from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

OutcomeKindLiteral = Literal["model_label", "risk_priority", "general"]


class OutcomeSubmitRequest(BaseModel):
    """Create one append-only outcome feedback row."""

    org_id: UUID | None = None
    asset_zone_id: str = Field(..., min_length=1, max_length=255)
    issue_key: str | None = Field(default=None, max_length=512)
    detection_type: str | None = Field(default=None, max_length=64)
    class_name: str | None = Field(default=None, max_length=128)
    subtype: str = Field(default="default", max_length=64)

    outcome_kind: OutcomeKindLiteral
    outcome_code: str = Field(..., min_length=1, max_length=64)
    notes: str | None = None
    context: dict[str, Any] | None = None
    actor: str | None = Field(default=None, max_length=255)

    target_inspection_id: UUID | None = None
    issue_state_id: UUID | None = None
    issue_state_event_id: UUID | None = None
    primary_detection_id: UUID | None = None
    detection_refs: list[dict[str, Any]] | None = None

    captured_priority_label: str | None = Field(default=None, max_length=32)
    captured_priority_score: float | None = None


class OutcomeFeedbackPublic(BaseModel):
    id: UUID
    created_at: datetime
    actor: str | None
    org_id: UUID | None
    asset_zone_id: str
    issue_key: str
    outcome_kind: str
    outcome_code: str
    notes: str | None
    context: dict[str, Any] | None
    target_inspection_id: UUID | None
    issue_state_id: UUID | None
    issue_state_event_id: UUID | None
    primary_detection_id: UUID | None
    detection_refs: list[dict[str, Any]] | None
    captured_priority_label: str | None
    captured_priority_score: float | None
    model_name: str | None
    model_version: str | None

    model_config = {"from_attributes": True}


class OutcomeListResponse(BaseModel):
    items: list[OutcomeFeedbackPublic]
    total: int
    limit: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)

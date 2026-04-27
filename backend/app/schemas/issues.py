from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

IssueStateLiteral = Literal["fixed", "monitoring", "deferred", "ignored"]


class IssueUpsertRequest(BaseModel):
    """Upsert body for ``PUT /issues/state``."""

    org_id: UUID | None = None
    asset_zone_id: str = Field(..., min_length=1, max_length=255)
    issue_key: str | None = Field(default=None, max_length=512)
    detection_type: str | None = Field(default=None, max_length=64)
    class_name: str | None = Field(default=None, max_length=128)
    subtype: str = Field(default="default", max_length=64)
    state: IssueStateLiteral
    notes: str | None = None
    updated_by: str | None = Field(default=None, max_length=255)
    last_target_inspection_id: UUID | None = None


class IssueStateEventPublic(BaseModel):
    id: UUID
    from_state: str | None
    to_state: str
    actor: str | None
    context: dict[str, object] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IssuePublic(BaseModel):
    id: UUID
    org_id: UUID | None
    asset_zone_id: str
    issue_key: str
    state: str
    notes: str | None
    updated_by: str | None
    last_target_inspection_id: UUID | None
    created_at: datetime
    updated_at: datetime
    events: list[IssueStateEventPublic] = Field(default_factory=list)


class IssueListResponse(BaseModel):
    items: list[IssuePublic]
    total: int
    limit: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)

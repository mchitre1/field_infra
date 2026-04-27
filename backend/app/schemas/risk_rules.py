from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RiskRulePublic(BaseModel):
    id: UUID
    org_id: UUID | None
    priority: int
    enabled: bool
    name: str
    match: dict[str, Any]
    effect: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskRuleCreate(BaseModel):
    org_id: UUID | None = None
    priority: int = Field(default=100, ge=0, le=1_000_000)
    enabled: bool = True
    name: str = Field(..., min_length=1, max_length=255)
    match: dict[str, Any]
    effect: dict[str, Any]


class RiskRulePatch(BaseModel):
    org_id: UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=1_000_000)
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    match: dict[str, Any] | None = None
    effect: dict[str, Any] | None = None


class RiskRuleListResponse(BaseModel):
    items: list[RiskRulePublic]
    total: int

"""CRUD-style API for persisted ``risk_rules`` (internal ops; no auth in v1)."""

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.models.risk_rule import RiskRule
from app.schemas.risk_rules import RiskRuleCreate, RiskRuleListResponse, RiskRulePatch, RiskRulePublic

router = APIRouter(prefix="/risk-rules", tags=["risk-rules"])


@router.get("", response_model=RiskRuleListResponse)
def list_risk_rules(
    db: DbSession,
    org_id: UUID | None = None,
    enabled: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RiskRuleListResponse:
    stmt = select(RiskRule)
    if org_id is not None:
        stmt = stmt.where(RiskRule.org_id == org_id)
    if enabled is not None:
        stmt = stmt.where(RiskRule.enabled == enabled)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(RiskRule.priority.asc(), RiskRule.id.asc()).limit(limit).offset(offset)
    ).all()
    return RiskRuleListResponse(items=[RiskRulePublic.model_validate(r) for r in rows], total=total)


@router.post("", response_model=RiskRulePublic, status_code=status.HTTP_201_CREATED)
def create_risk_rule(db: DbSession, body: RiskRuleCreate) -> RiskRule:
    row = RiskRule(
        id=uuid.uuid4(),
        org_id=body.org_id,
        priority=body.priority,
        enabled=body.enabled,
        name=body.name.strip(),
        match=dict(body.match),
        effect=dict(body.effect),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{rule_id}", response_model=RiskRulePublic)
def patch_risk_rule(rule_id: UUID, db: DbSession, body: RiskRulePatch) -> RiskRule:
    row = db.get(RiskRule, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk rule not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = str(data["name"]).strip()
    if "priority" in data and data["priority"] is not None:
        row.priority = int(data["priority"])
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])
    if "org_id" in data:
        row.org_id = data["org_id"]
    if "match" in data and data["match"] is not None:
        row.match = dict(data["match"])
    if "effect" in data and data["effect"] is not None:
        row.effect = dict(data["effect"])
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

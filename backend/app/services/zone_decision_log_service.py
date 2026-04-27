"""Append-only zone decision log for audit export."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.zone_decision_log import ZoneDecisionLog

RATIONALE_PAYLOAD_CHARS = 8000


def append_zone_decision_log(
    *,
    db: Session,
    org_id: uuid.UUID | None,
    asset_zone_id: str,
    event_type: str,
    payload: dict[str, Any],
    inspection_id: uuid.UUID | None = None,
    issue_key: str | None = None,
    issue_state_event_id: uuid.UUID | None = None,
    outcome_feedback_id: uuid.UUID | None = None,
    maintenance_recommendation_id: uuid.UUID | None = None,
) -> ZoneDecisionLog:
    """Single insert; caller commits."""
    row = ZoneDecisionLog(
        id=uuid.uuid4(),
        org_id=org_id,
        asset_zone_id=asset_zone_id.strip(),
        issue_key=issue_key.strip() if issue_key else None,
        inspection_id=inspection_id,
        event_type=event_type.strip(),
        payload=payload,
        issue_state_event_id=issue_state_event_id,
        outcome_feedback_id=outcome_feedback_id,
        maintenance_recommendation_id=maintenance_recommendation_id,
    )
    db.add(row)
    return row


def truncate_rationale_for_payload(rationale: list[dict[str, Any]] | None) -> Any:
    if not rationale:
        return []
    raw = json.dumps(rationale)
    if len(raw) <= RATIONALE_PAYLOAD_CHARS:
        return rationale
    return {"truncated": True, "preview": raw[:RATIONALE_PAYLOAD_CHARS]}


def list_zone_decision_log(
    *,
    db: Session,
    asset_zone_id: str,
    org_id: uuid.UUID | None = None,
    inspection_id: uuid.UUID | None = None,
    event_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ZoneDecisionLog], int]:
    """Newest first. Omitting ``org_id`` limits to rows with ``org_id IS NULL`` (global bucket), matching ``GET /issues`` / ``GET /outcomes``."""
    stmt = select(ZoneDecisionLog).where(ZoneDecisionLog.asset_zone_id == asset_zone_id.strip())
    if org_id is not None:
        stmt = stmt.where(ZoneDecisionLog.org_id == org_id)
    else:
        stmt = stmt.where(ZoneDecisionLog.org_id.is_(None))
    if inspection_id is not None:
        stmt = stmt.where(ZoneDecisionLog.inspection_id == inspection_id)
    if event_type is not None:
        stmt = stmt.where(ZoneDecisionLog.event_type == event_type.strip())
    if created_from is not None:
        stmt = stmt.where(ZoneDecisionLog.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(ZoneDecisionLog.created_at <= created_to)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(ZoneDecisionLog.created_at.desc(), ZoneDecisionLog.id.desc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt).all())
    return rows, int(total)

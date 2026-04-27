"""Upsert and list operator issue workflow states."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.inspection import Inspection
from app.models.issue_state import IssueState, IssueStateEvent
from app.services.issue_key import build_issue_key
from app.services.zone_decision_log_service import append_zone_decision_log

ALLOWED_STATES = frozenset({"fixed", "monitoring", "deferred", "ignored"})


def org_scope_for(org_id: uuid.UUID | None) -> str:
    """Stable bucket for unique constraint (NULL org → ``global``)."""
    return str(org_id) if org_id is not None else "global"


def _apply_issue_filters(
    stmt,
    *,
    org_id: uuid.UUID | None,
    asset_zone_id: str | None,
    state: str | None,
):
    if org_id is not None:
        stmt = stmt.where(IssueState.org_scope == org_scope_for(org_id))
    else:
        stmt = stmt.where(IssueState.org_scope == "global")
    if asset_zone_id is not None:
        stmt = stmt.where(IssueState.asset_zone_id == asset_zone_id.strip())
    if state is not None:
        st = state.strip().lower()
        if st not in ALLOWED_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid state filter; allowed: {', '.join(sorted(ALLOWED_STATES))}",
            )
        stmt = stmt.where(IssueState.state == st)
    return stmt


def upsert_issue_state(
    *,
    db: Session,
    org_id: uuid.UUID | None,
    asset_zone_id: str,
    issue_key: str,
    state: str,
    notes: str | None,
    updated_by: str | None,
    last_target_inspection_id: uuid.UUID | None,
) -> IssueState:
    st = state.strip().lower()
    if st not in ALLOWED_STATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid state; allowed: {', '.join(sorted(ALLOWED_STATES))}",
        )
    zone = asset_zone_id.strip()
    key = issue_key.strip()
    if not zone or not key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="asset_zone_id and issue_key must be non-empty",
        )
    if last_target_inspection_id is not None and db.get(Inspection, last_target_inspection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="last_target_inspection_id not found")

    scope = org_scope_for(org_id)
    row = db.scalar(
        select(IssueState).where(
            IssueState.org_scope == scope,
            IssueState.asset_zone_id == zone,
            IssueState.issue_key == key,
        )
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = IssueState(
            id=uuid.uuid4(),
            org_scope=scope,
            org_id=org_id,
            asset_zone_id=zone,
            issue_key=key,
            state=st,
            notes=notes,
            updated_by=updated_by,
            last_target_inspection_id=last_target_inspection_id,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        ev_id = uuid.uuid4()
        db.add(
            IssueStateEvent(
                id=ev_id,
                issue_state_id=row.id,
                from_state=None,
                to_state=st,
                actor=updated_by,
                context=None,
            )
        )
        summary = f"Issue {key} in {zone}: new → {st}"
        refs: dict[str, object | None] = {
            "issue_state_id": str(row.id),
            "issue_state_event_id": str(ev_id),
            "from_state": None,
            "to_state": st,
            "actor": updated_by,
            "issue_key": key,
        }
        append_zone_decision_log(
            db=db,
            org_id=org_id,
            asset_zone_id=zone,
            event_type="issue_state_transition",
            issue_key=key,
            inspection_id=last_target_inspection_id,
            issue_state_event_id=ev_id,
            payload={"summary": summary, "refs": refs},
        )
        db.commit()
        db.refresh(row)
        return row

    prev = row.state
    row.state = st
    row.org_scope = scope
    row.org_id = org_id
    if notes is not None:
        row.notes = notes
    if updated_by is not None:
        row.updated_by = updated_by
    if last_target_inspection_id is not None:
        row.last_target_inspection_id = last_target_inspection_id
    row.updated_at = now
    db.add(row)
    if prev != st:
        ev_id = uuid.uuid4()
        db.add(
            IssueStateEvent(
                id=ev_id,
                issue_state_id=row.id,
                from_state=prev,
                to_state=st,
                actor=updated_by,
                context=None,
            )
        )
        summary = f"Issue {key} in {zone}: {prev} → {st}"
        refs = {
            "issue_state_id": str(row.id),
            "issue_state_event_id": str(ev_id),
            "from_state": prev,
            "to_state": st,
            "actor": updated_by,
            "issue_key": key,
        }
        append_zone_decision_log(
            db=db,
            org_id=org_id,
            asset_zone_id=zone,
            event_type="issue_state_transition",
            issue_key=key,
            inspection_id=last_target_inspection_id,
            issue_state_event_id=ev_id,
            payload={"summary": summary, "refs": refs},
        )
    db.commit()
    db.refresh(row)
    return row


def list_issue_states(
    *,
    db: Session,
    org_id: uuid.UUID | None = None,
    asset_zone_id: str | None = None,
    state: str | None = None,
    include_events: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[IssueState], int]:
    """Return paginated ``IssueState`` rows (newest ``updated_at`` first) and total count."""
    base = select(IssueState)
    base = _apply_issue_filters(base, org_id=org_id, asset_zone_id=asset_zone_id, state=state)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = base.order_by(IssueState.updated_at.desc(), IssueState.id.asc()).limit(limit).offset(offset)
    if include_events:
        stmt = stmt.options(selectinload(IssueState.events))
    rows = list(db.scalars(stmt).all())
    return rows, total

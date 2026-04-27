"""Append-only inspection status transition logging."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inspection import InspectionStatus
from app.models.inspection_history_event import InspectionHistoryEvent


def record_inspection_status_transition(
    *,
    db: Session,
    inspection_id: uuid.UUID,
    from_status: InspectionStatus,
    to_status: InspectionStatus,
    source: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Insert one history row when status changes; caller must ``commit``."""
    if from_status == to_status:
        return
    db.add(
        InspectionHistoryEvent(
            id=uuid.uuid4(),
            inspection_id=inspection_id,
            from_status=from_status.value,
            to_status=to_status.value,
            source=source,
            context=context,
        )
    )


def list_inspection_history(
    *,
    db: Session,
    inspection_id: uuid.UUID,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[InspectionHistoryEvent], int]:
    """Paginated status transitions for one inspection; oldest ``created_at`` first."""
    base = select(InspectionHistoryEvent).where(InspectionHistoryEvent.inspection_id == inspection_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = (
        base.order_by(InspectionHistoryEvent.created_at.asc(), InspectionHistoryEvent.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(db.scalars(stmt).all())
    return rows, int(total)

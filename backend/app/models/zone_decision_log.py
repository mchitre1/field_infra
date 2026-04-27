"""Append-only audit rows for operator and system decisions per asset zone."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ZoneDecisionLog(Base):
    """Denormalized decision log; FKs may null out on upstream deletes—``payload`` is authoritative."""

    __tablename__ = "zone_decision_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    asset_zone_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    issue_state_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("issue_state_events.id", ondelete="SET NULL"), nullable=True
    )
    outcome_feedback_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("outcome_feedbacks.id", ondelete="SET NULL"), nullable=True
    )
    maintenance_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("maintenance_recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )

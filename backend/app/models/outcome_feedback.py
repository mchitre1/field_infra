"""Append-only operator outcome rows for model training and risk-score priors."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutcomeFeedback(Base):
    """Structured feedback tied to zone + issue identity (and optional inspection/detection anchors)."""

    __tablename__ = "outcome_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    org_scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    asset_zone_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    outcome_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    outcome_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    target_inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    issue_state_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("issue_states.id", ondelete="SET NULL"), nullable=True, index=True
    )
    issue_state_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("issue_state_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    primary_detection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("detections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    detection_refs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    captured_priority_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    captured_priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

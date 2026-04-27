import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IssueStateEvent(Base):
    """Append-only history of issue state transitions."""

    __tablename__ = "issue_state_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    issue_state_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("issue_states.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    issue_state: Mapped["IssueState"] = relationship("IssueState", back_populates="events")


class IssueState(Base):
    """Operator-owned workflow state for a logical issue (zone + issue_key)."""

    __tablename__ = "issue_states"
    __table_args__ = (
        UniqueConstraint("org_scope", "asset_zone_id", "issue_key", name="uq_issue_states_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    org_scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    asset_zone_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_target_inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    events: Mapped[list[IssueStateEvent]] = relationship(
        IssueStateEvent,
        back_populates="issue_state",
        cascade="all, delete-orphan",
        order_by=IssueStateEvent.created_at.asc(),
    )

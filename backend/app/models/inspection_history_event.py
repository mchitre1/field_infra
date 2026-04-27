"""Append-only inspection status transitions for linear audit."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InspectionHistoryEvent(Base):
    __tablename__ = "inspection_history_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(64), nullable=False)
    to_status: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

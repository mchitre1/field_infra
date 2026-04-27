import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskRule(Base):
    """Declarative risk adjustments evaluated during maintenance recommendation scoring."""

    __tablename__ = "risk_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    match: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    effect: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MaintenanceRecommendation(Base):
    """One ranked maintenance line item for a target inspection (worker-generated, replace per run)."""

    __tablename__ = "maintenance_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    target_inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    asset_zone_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_label: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False)
    action_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    rationale: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    sla_target_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_days_suggested: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

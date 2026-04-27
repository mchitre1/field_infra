import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DetectionType(str, enum.Enum):
    asset = "asset"
    defect = "defect"
    environmental_hazard = "environmental_hazard"


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), index=True
    )
    frame_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frames.id", ondelete="CASCADE"), index=True
    )
    detection_type: Mapped[DetectionType] = mapped_column(
        Enum(DetectionType, name="detection_type", native_enum=False, length=64),
        index=True,
        nullable=False,
    )
    class_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_xmin: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_ymin: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_xmax: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_ymax: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    extra_attributes: Mapped[dict[str, Any] | None] = mapped_column(
        "attributes", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

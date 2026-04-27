import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceType(str, enum.Enum):
    drone = "drone"
    mobile = "mobile"
    fixed_camera = "fixed_camera"


class InspectionStatus(str, enum.Enum):
    received = "received"
    stored = "stored"
    queued = "queued"
    failed = "failed"
    stored_pending_queue = "stored_pending_queue"
    processing_frames = "processing_frames"
    frames_extracted = "frames_extracted"
    frames_failed = "frames_failed"
    processing_detections = "processing_detections"
    detections_ready = "detections_ready"
    detections_failed = "detections_failed"
    processing_alignment = "processing_alignment"
    alignment_ready = "alignment_ready"
    alignment_failed = "alignment_failed"


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", native_enum=False, length=32),
        nullable=False,
    )
    site_hint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    asset_hint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    capture_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(nullable=True)
    frame_count: Mapped[int | None] = mapped_column(nullable=True)
    video_duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    video_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detection_count: Mapped[int | None] = mapped_column(nullable=True)
    aligned_pair_count: Mapped[int | None] = mapped_column(nullable=True)
    change_event_count: Mapped[int | None] = mapped_column(nullable=True)

    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="inspection_status", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    last_queue_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

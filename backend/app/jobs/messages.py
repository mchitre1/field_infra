from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.inspection import SourceType


class IngestJobMessage(BaseModel):
    """JSON body published to SQS after a successful store (multipart or presign complete)."""

    inspection_id: UUID
    s3_uri: str
    content_type: str
    source_type: SourceType
    capture_timestamp: datetime | None = None
    site_hint: str | None = None
    asset_hint: str | None = None
    frame_extraction: dict[str, str | int | float] = Field(
        default_factory=lambda: {"mode": "default", "fps": 1.0, "max_frames": 300},
        description="Hints for downstream frame extraction (v1 placeholder).",
    )
    detection: dict[str, Any] = Field(
        default_factory=lambda: {
            "mode": "default",
            "threshold": 0.35,
            "model_name": "yolo",
            "model_version": "v1",
            "enabled_classes": [],
        },
        description="Hints for downstream detection/classification stage.",
    )

from datetime import datetime
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
    frame_extraction: dict[str, str] = Field(
        default_factory=lambda: {"mode": "default"},
        description="Hints for downstream frame extraction (v1 placeholder).",
    )

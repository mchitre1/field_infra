from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FramePublic(BaseModel):
    """Public frame metadata returned by `GET /ingest/{inspection_id}/frames`."""

    id: UUID
    inspection_id: UUID
    frame_index: int
    frame_timestamp_ms: int
    s3_bucket: str
    s3_key: str
    width: int | None = None
    height: int | None = None
    capture_timestamp: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_type: str
    site_hint: str | None = None
    asset_hint: str | None = None

    model_config = {"from_attributes": True}

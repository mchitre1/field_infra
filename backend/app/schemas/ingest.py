from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class SourceTypeSchema(str, Enum):
    drone = "drone"
    mobile = "mobile"
    fixed_camera = "fixed_camera"


class IngestMetadata(BaseModel):
    source_type: SourceTypeSchema
    org_id: UUID | None = None
    site_hint: str | None = Field(default=None, max_length=512)
    asset_hint: str | None = Field(default=None, max_length=512)
    capture_timestamp: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None


class PresignRequest(IngestMetadata):
    content_type: str = Field(..., min_length=3, max_length=255)
    filename: str = Field(..., min_length=1, max_length=512)


class PresignResponse(BaseModel):
    inspection_id: UUID
    upload_url: str
    s3_key: str
    headers: dict[str, str]


class CompleteIngestRequest(BaseModel):
    """Optional check that the client still agrees on MIME type; S3 HeadObject is authoritative for the stored object."""

    expected_content_type: str | None = None


class InspectionPublic(BaseModel):
    id: UUID
    status: str
    s3_bucket: str
    s3_key: str
    content_type: str
    byte_size: int | None
    frame_count: int | None = None
    video_duration_ms: int | None = None
    video_fps: float | None = None
    detection_count: int | None = None
    aligned_pair_count: int | None = None
    change_event_count: int | None = None
    progression_metric_count: int | None = None

    model_config = {"from_attributes": True}

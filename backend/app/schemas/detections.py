from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DetectionPublic(BaseModel):
    """Detection payload returned by inspection/frame detection query endpoints."""

    id: UUID
    inspection_id: UUID
    frame_id: UUID
    detection_type: str
    class_name: str
    confidence: float
    bbox_xmin: float
    bbox_ymin: float
    bbox_xmax: float
    bbox_ymax: float
    geometry: dict[str, Any] | None = None
    attributes: dict[str, Any] | None = Field(
        default=None, validation_alias="extra_attributes"
    )
    model_name: str
    model_version: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaginatedDetectionsResponse(BaseModel):
    """Standard paginated envelope for detection list endpoints."""

    items: list[DetectionPublic]
    total: int
    limit: int
    offset: int

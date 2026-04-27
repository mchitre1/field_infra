from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "video/mp4",
        "video/quicktime",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/iie",
    )
    aws_region: str = Field(default="us-east-1")
    s3_bucket: str = Field(default="")
    frames_bucket: str = Field(default="")
    s3_key_prefix: str = Field(default="")
    sqs_queue_url: str = Field(default="")
    kms_key_id: str | None = Field(default=None)

    max_upload_bytes: int = Field(default=100 * 1024 * 1024)
    allowed_content_types: frozenset[str] = Field(default=_DEFAULT_TYPES)
    presign_expires_seconds: int = Field(default=3600)
    frame_extraction_fps: float = Field(default=1.0)
    max_frames_per_inspection: int = Field(default=300)
    ffmpeg_bin: str = Field(default="ffmpeg")
    ffprobe_bin: str = Field(default="ffprobe")
    inference_model_name: str = Field(default="yolo")
    inference_model_version: str = Field(default="v1")
    inference_confidence_threshold: float = Field(default=0.35)
    inference_device: str = Field(default="cpu")
    inference_batch_size: int = Field(default=16)
    sam_model_name: str | None = Field(default=None)
    alignment_time_tolerance_seconds: int = Field(default=86400)
    alignment_geo_tolerance_meters: float = Field(default=250.0)
    alignment_iou_threshold: float = Field(default=0.3)
    alignment_min_confidence: float = Field(default=0.35)
    alignment_max_centroid_norm_distance: float = Field(
        default=0.55,
        description="Max normalized image-space distance between detection centroids for a match.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

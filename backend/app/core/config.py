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

    progression_min_time_delta_seconds: int = Field(
        default=3600,
        description="Minimum seconds between baseline and target ref time before emitting rate metrics.",
    )
    progression_crack_metric: str = Field(
        default="bbox_width",
        description="Size proxy for crack metrics: bbox_width | bbox_area | max_extent.",
    )
    progression_vegetation_metric: str = Field(
        default="bbox_area",
        description="Vegetation size proxy (v1 uses normalized bbox area only).",
    )

    timeline_max_entries: int = Field(
        default=2000,
        ge=1,
        description="Max unified timeline rows returned (newest slice when exceeded).",
    )
    trend_max_points: int = Field(
        default=500,
        ge=1,
        description="Max progression samples per trend response (most recent when exceeded).",
    )
    trend_min_span_days: float = Field(
        default=1.0,
        ge=0.0,
        description="Minimum span in days (first→last effective time) before emitting simple_slope_per_day.",
    )
    change_map_max_features: int = Field(
        default=5000,
        ge=1,
        description="Max alignment pairs processed per change-map request (oldest pairs dropped when exceeded).",
    )

    recommend_defect_confidence_floor: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Defect detections at or above this max-zone confidence add risk score.",
    )
    recommend_weight_defect_confidence: float = Field(
        default=40.0,
        description="Weight multiplied by max defect confidence in the zone (when above floor).",
    )
    recommend_weight_change_appeared: float = Field(
        default=18.0,
        description="Score bump per change event with event_type=appeared.",
    )
    recommend_weight_change_disappeared: float = Field(
        default=10.0,
        description="Score bump per change event with event_type=disappeared.",
    )
    recommend_weight_change_other: float = Field(
        default=5.0,
        description="Score bump per other change event type.",
    )
    recommend_crack_growth_rate_floor: float = Field(
        default=0.0005,
        description="crack_growth_rate values above this add progression risk.",
    )
    recommend_weight_crack_growth: float = Field(
        default=35.0,
        description="Weight multiplied by crack_growth_rate when above floor (capped internally).",
    )
    recommend_vegetation_delta_floor: float = Field(
        default=0.005,
        description="vegetation_encroachment_delta values above this add progression risk.",
    )
    recommend_weight_vegetation_delta: float = Field(
        default=22.0,
        description="Weight multiplied by vegetation_encroachment_delta when above floor (capped).",
    )
    recommend_band_critical_min: float = Field(
        default=80.0,
        description="priority_score >= this maps to critical.",
    )
    recommend_band_high_min: float = Field(
        default=45.0,
        description="priority_score >= this maps to high (if not critical).",
    )
    recommend_band_medium_min: float = Field(
        default=15.0,
        description="priority_score >= this maps to medium.",
    )
    recommend_sla_days_critical: float = Field(default=7.0, ge=0.0)
    recommend_sla_days_high: float = Field(default=30.0, ge=0.0)
    recommend_sla_days_medium: float = Field(default=90.0, ge=0.0)
    recommend_sla_days_low: float = Field(default=180.0, ge=0.0)
    recommend_max_per_inspection: int = Field(
        default=100,
        ge=1,
        le=5000,
        description="Max maintenance recommendation rows persisted per target inspection.",
    )

    risk_rules_default_org_behavior: str = Field(
        default="merge_global_then_org",
        description="merge_global_then_org: org-specific rules first, then global; global_only: ignore org rows.",
    )
    risk_rules_max_rows_per_eval: int = Field(
        default=500,
        ge=1,
        le=10_000,
        description="Max risk_rule rows loaded per recommendation run (after merge ordering).",
    )
    risk_rules_score_max: float = Field(
        default=500.0,
        ge=1.0,
        description="Clamp final zone score after risk rule multipliers/additions.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

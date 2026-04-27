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
    s3_key_prefix: str = Field(default="")
    sqs_queue_url: str = Field(default="")
    kms_key_id: str | None = Field(default=None)

    max_upload_bytes: int = Field(default=100 * 1024 * 1024)
    allowed_content_types: frozenset[str] = Field(default=_DEFAULT_TYPES)
    presign_expires_seconds: int = Field(default=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()

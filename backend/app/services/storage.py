from __future__ import annotations

import logging
import re
from typing import Any, BinaryIO
from uuid import UUID

from botocore.exceptions import ClientError

from app.core.config import Settings

log = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def build_object_key(
    *,
    settings: Settings,
    org_id: UUID | None,
    inspection_id: UUID,
    original_filename: str,
) -> str:
    """S3 object key: optional prefix + ``{org_id|org-unknown}/{inspection_id}/{safe_filename}``."""
    raw = original_filename.rsplit("/", maxsplit=1)[-1].strip() or "upload.bin"
    safe = _SAFE_NAME.sub("_", raw)[:255]
    org_segment = str(org_id) if org_id else "org-unknown"
    parts: list[str] = []
    if settings.s3_key_prefix:
        parts.append(settings.s3_key_prefix.strip("/"))
    parts.extend([org_segment, str(inspection_id), safe])
    return "/".join(parts)


def build_frame_object_key(
    *,
    settings: Settings,
    org_id: UUID | None,
    inspection_id: UUID,
    frame_index: int,
) -> str:
    org_segment = str(org_id) if org_id else "org-unknown"
    parts: list[str] = []
    if settings.s3_key_prefix:
        parts.append(settings.s3_key_prefix.strip("/"))
    parts.extend([org_segment, str(inspection_id), "frames", f"{frame_index:06d}.jpg"])
    return "/".join(parts)


def put_fileobj(
    *,
    settings: Settings,
    s3_client: Any,
    bucket: str,
    key: str,
    fileobj: BinaryIO,
    content_type: str,
    byte_size: int,
) -> None:
    """Upload bytes with ``Content-Type`` and optional SSE-KMS when ``kms_key_id`` is set."""
    extra: dict[str, str] = {"ContentType": content_type}
    if settings.kms_key_id:
        extra["ServerSideEncryption"] = "aws:kms"
        extra["SSEKMSKeyId"] = settings.kms_key_id

    s3_client.upload_fileobj(
        fileobj,
        bucket,
        key,
        ExtraArgs=extra,
    )
    log.info("Stored s3://%s/%s (%s bytes)", bucket, key, byte_size)


def put_bytes(
    *,
    settings: Settings,
    s3_client: Any,
    bucket: str,
    key: str,
    content: bytes,
    content_type: str,
) -> None:
    extra: dict[str, str] = {"ContentType": content_type}
    if settings.kms_key_id:
        extra["ServerSideEncryption"] = "aws:kms"
        extra["SSEKMSKeyId"] = settings.kms_key_id
    s3_client.put_object(Bucket=bucket, Key=key, Body=content, **extra)


def head_object(*, s3_client: Any, bucket: str, key: str) -> dict:
    """Return S3 HeadObject response dict; map missing object to ``FileNotFoundError``."""
    try:
        return s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "404":
            raise FileNotFoundError(key) from e
        raise


def get_object_bytes(*, s3_client: Any, bucket: str, key: str) -> bytes:
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()
    if not isinstance(body, (bytes, bytearray)):
        return bytes(body)
    return bytes(body)


def delete_object(*, s3_client: Any, bucket: str, key: str) -> None:
    """Best-effort removal (e.g. compensating delete after failed DB commit)."""
    s3_client.delete_object(Bucket=bucket, Key=key)


def generate_presigned_put(
    *,
    settings: Settings,
    s3_client: Any,
    bucket: str,
    key: str,
    content_type: str,
) -> tuple[str, dict[str, str]]:
    """Return (presigned PUT URL, headers the client should send with the upload)."""
    params: dict[str, str] = {
        "Bucket": bucket,
        "Key": key,
        "ContentType": content_type,
    }
    if settings.kms_key_id:
        params["ServerSideEncryption"] = "aws:kms"
        params["SSEKMSKeyId"] = settings.kms_key_id

    url: str = s3_client.generate_presigned_url(
        "put_object",
        Params=params,
        ExpiresIn=settings.presign_expires_seconds,
        HttpMethod="PUT",
    )
    headers = {"Content-Type": content_type}
    if settings.kms_key_id:
        headers["x-amz-server-side-encryption"] = "aws:kms"
        headers["x-amz-server-side-encryption-aws-kms-key-id"] = settings.kms_key_id
    return url, headers

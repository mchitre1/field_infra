from __future__ import annotations

import logging
import tempfile
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.jobs.publisher import publish_ingest_job
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.schemas.ingest import PresignRequest, PresignResponse
from app.services import storage

log = logging.getLogger(__name__)

CHUNK = 1024 * 1024


def _normalize_content_type(value: str | None) -> str | None:
    if value is None:
        return None
    return value.split(";", 1)[0].strip().lower()


def _ensure_content_type_allowed(settings: Settings, content_type: str) -> None:
    if content_type not in settings.allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {content_type}",
        )


async def spool_upload_limited(file: UploadFile, settings: Settings) -> tuple[tempfile.SpooledTemporaryFile[bytes], int]:
    """Read upload into a spooled file, enforcing ``max_upload_bytes``."""
    spool: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(max_size=settings.max_upload_bytes + 1)
    total = 0
    try:
        while True:
            chunk = await file.read(CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Upload exceeds configured limit",
                )
            spool.write(chunk)
        spool.seek(0)
        return spool, total
    except Exception:
        spool.close()
        raise


async def ingest_multipart_upload(
    *,
    settings: Settings,
    db: Session,
    s3_client: object,
    sqs_client: object,
    file: UploadFile,
    source_type: SourceType,
    org_id: UUID | None,
    site_hint: str | None,
    asset_hint: str | None,
    capture_timestamp,
    latitude: float | None,
    longitude: float | None,
) -> Inspection:
    """Stream upload into S3, commit ``Inspection`` as ``stored``, then ``publish_ingest_job``.

    On DB failure after a successful S3 put, attempts best-effort deletion of the orphan object.
    """
    if not settings.s3_bucket:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="S3 bucket not configured")

    content_type = file.content_type or "application/octet-stream"
    _ensure_content_type_allowed(settings, content_type)

    inspection_id = uuid4()
    filename = file.filename or "upload.bin"
    key = storage.build_object_key(
        settings=settings,
        org_id=org_id,
        inspection_id=inspection_id,
        original_filename=filename,
    )

    spool, byte_size = await spool_upload_limited(file, settings)
    try:
        storage.put_fileobj(
            settings=settings,
            s3_client=s3_client,
            bucket=settings.s3_bucket,
            key=key,
            fileobj=spool,
            content_type=content_type,
            byte_size=byte_size,
        )
    except Exception:
        log.exception("S3 upload failed for inspection %s", inspection_id)
        spool.close()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Object storage failed")
    finally:
        spool.close()

    inspection = Inspection(
        id=inspection_id,
        org_id=org_id,
        source_type=source_type,
        site_hint=site_hint,
        asset_hint=asset_hint,
        capture_timestamp=capture_timestamp,
        s3_bucket=settings.s3_bucket,
        s3_key=key,
        content_type=content_type,
        byte_size=byte_size,
        status=InspectionStatus.stored,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(inspection)
    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception("DB commit failed after S3 store for inspection %s", inspection_id)
        try:
            storage.delete_object(
                s3_client=s3_client, bucket=settings.s3_bucket, key=key
            )
        except Exception:
            log.exception(
                "Failed to delete orphan S3 object s3://%s/%s after DB failure",
                settings.s3_bucket,
                key,
            )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist inspection",
        ) from None
    db.refresh(inspection)

    publish_ingest_job(settings=settings, db=db, inspection=inspection, sqs_client=sqs_client)
    db.refresh(inspection)
    return inspection


def create_presigned_ingest(
    *,
    settings: Settings,
    db: Session,
    s3_client: object,
    body: PresignRequest,
) -> PresignResponse:
    """Build a presigned PUT, then persist a ``received`` row (presign runs before commit)."""
    if not settings.s3_bucket:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="S3 bucket not configured")

    _ensure_content_type_allowed(settings, body.content_type)

    inspection_id = uuid4()
    org = body.org_id
    key = storage.build_object_key(
        settings=settings,
        org_id=org,
        inspection_id=inspection_id,
        original_filename=body.filename,
    )

    try:
        url, headers = storage.generate_presigned_put(
            settings=settings,
            s3_client=s3_client,
            bucket=settings.s3_bucket,
            key=key,
            content_type=body.content_type,
        )
    except Exception:
        log.exception("Presigned URL generation failed for inspection %s", inspection_id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Could not create upload URL",
        ) from None

    inspection = Inspection(
        id=inspection_id,
        org_id=org,
        source_type=SourceType(body.source_type.value),
        site_hint=body.site_hint,
        asset_hint=body.asset_hint,
        capture_timestamp=body.capture_timestamp,
        s3_bucket=settings.s3_bucket,
        s3_key=key,
        content_type=body.content_type,
        byte_size=None,
        status=InspectionStatus.received,
        latitude=body.latitude,
        longitude=body.longitude,
    )
    db.add(inspection)
    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception("DB commit failed after presign for inspection %s", inspection_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist inspection",
        ) from None
    return PresignResponse(inspection_id=inspection_id, upload_url=url, s3_key=key, headers=headers)


def complete_presigned_ingest(
    *,
    settings: Settings,
    db: Session,
    s3_client: object,
    sqs_client: object,
    inspection_id: UUID,
    expected_content_type: str | None,
) -> Inspection:
    """Head S3 to confirm object, align ``ContentType`` with the inspection row, set ``stored``, enqueue."""
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    if inspection.status != InspectionStatus.received:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Inspection is not awaiting client upload")

    if expected_content_type is not None:
        if (
            _normalize_content_type(expected_content_type)
            != _normalize_content_type(inspection.content_type)
        ):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="content type mismatch"
            )

    try:
        head = storage.head_object(s3_client=s3_client, bucket=inspection.s3_bucket, key=inspection.s3_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Object not found in storage") from None
    except Exception:
        log.exception("head_object failed for %s", inspection_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Storage verification failed")

    head_ct = head.get("ContentType")
    if not head_ct:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Stored object missing content type metadata",
        )
    if _normalize_content_type(head_ct) != _normalize_content_type(inspection.content_type):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Stored object content type does not match inspection",
        )

    size = int(head["ContentLength"])
    if size > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="Stored object exceeds limit")

    inspection.byte_size = size
    inspection.status = InspectionStatus.stored
    db.add(inspection)
    db.commit()
    db.refresh(inspection)

    publish_ingest_job(settings=settings, db=db, inspection=inspection, sqs_client=sqs_client)
    db.refresh(inspection)
    return inspection

"""HTTP handlers for inspection media ingestion (multipart and presigned S3)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile, status

from app.api.deps import DbSession, S3Client, SettingsDep, SQSClient
from app.models.inspection import SourceType
from app.schemas.ingest import CompleteIngestRequest, InspectionPublic, PresignRequest, PresignResponse
from app.services import ingest as ingest_service

router = APIRouter(tags=["ingest"])


def _parse_source_type(raw: str) -> SourceType:
    try:
        return SourceType(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid source_type: {raw}",
        ) from None


@router.post("/ingest/upload", response_model=InspectionPublic)
async def upload_inspection(
    settings: SettingsDep,
    db: DbSession,
    s3_client: S3Client,
    sqs_client: SQSClient,
    file: UploadFile = File(...),
    source_type: Annotated[str, Form()] = ...,
    org_id: Annotated[UUID | None, Form()] = None,
    site_hint: Annotated[str | None, Form()] = None,
    asset_hint: Annotated[str | None, Form()] = None,
    capture_timestamp: Annotated[datetime | None, Form()] = None,
    latitude: Annotated[float | None, Form()] = None,
    longitude: Annotated[float | None, Form()] = None,
):
    """Accept a multipart file plus form metadata, store in S3, persist row, enqueue when SQS is configured."""
    st = _parse_source_type(source_type)
    row = await ingest_service.ingest_multipart_upload(
        settings=settings,
        db=db,
        s3_client=s3_client,
        sqs_client=sqs_client,
        file=file,
        source_type=st,
        org_id=org_id,
        site_hint=site_hint,
        asset_hint=asset_hint,
        capture_timestamp=capture_timestamp,
        latitude=latitude,
        longitude=longitude,
    )
    return InspectionPublic.model_validate(row)


@router.post("/ingest/presign", response_model=PresignResponse)
def presign_inspection(
    settings: SettingsDep,
    db: DbSession,
    s3_client: S3Client,
    body: PresignRequest,
):
    """Create a ``received`` inspection and return a presigned PUT URL for direct upload to S3."""
    return ingest_service.create_presigned_ingest(
        settings=settings, db=db, s3_client=s3_client, body=body
    )


@router.post("/ingest/{inspection_id}/complete", response_model=InspectionPublic)
def complete_inspection(
    inspection_id: UUID,
    settings: SettingsDep,
    db: DbSession,
    s3_client: S3Client,
    sqs_client: SQSClient,
    body: CompleteIngestRequest | None = Body(None),
):
    """Verify the S3 object for a presigned upload, update size and status, then enqueue like multipart."""
    expected_ct = body.expected_content_type if body else None
    row = ingest_service.complete_presigned_ingest(
        settings=settings,
        db=db,
        s3_client=s3_client,
        sqs_client=sqs_client,
        inspection_id=inspection_id,
        expected_content_type=expected_ct,
    )
    return InspectionPublic.model_validate(row)

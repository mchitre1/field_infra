"""HTTP handlers for inspection media ingestion (multipart and presigned S3)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DbSession, S3Client, SettingsDep, SQSClient
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import SourceType
from app.schemas.detections import DetectionPublic, PaginatedDetectionsResponse
from app.schemas.frames import FramePublic
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


@router.get("/ingest/{inspection_id}/frames", response_model=list[FramePublic])
def list_frames(
    inspection_id: UUID,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List extracted frames for an inspection ordered by frame index."""
    rows = db.scalars(
        select(Frame)
        .where(Frame.inspection_id == inspection_id)
        .order_by(Frame.frame_index.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [FramePublic.model_validate(r) for r in rows]


@router.get(
    "/ingest/{inspection_id}/detections",
    response_model=PaginatedDetectionsResponse,
)
def list_detections(
    inspection_id: UUID,
    db: DbSession,
    detection_type: DetectionType | None = None,
    class_name: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    frame_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
 ) -> PaginatedDetectionsResponse:
    """List detections for an inspection with optional type/class/confidence/frame filters."""
    stmt = select(Detection).where(Detection.inspection_id == inspection_id)
    if detection_type is not None:
        stmt = stmt.where(Detection.detection_type == detection_type)
    if class_name is not None:
        stmt = stmt.where(func.lower(Detection.class_name) == class_name.strip().lower())
    if min_confidence is not None:
        stmt = stmt.where(Detection.confidence >= min_confidence)
    if frame_id is not None:
        stmt = stmt.where(Detection.frame_id == frame_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Detection.created_at.asc(), Detection.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PaginatedDetectionsResponse(
        items=[DetectionPublic.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/ingest/{inspection_id}/frames/{frame_id}/detections",
    response_model=PaginatedDetectionsResponse,
)
def list_frame_detections(
    inspection_id: UUID,
    frame_id: UUID,
    db: DbSession,
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedDetectionsResponse:
    """List detections for a single frame within an inspection."""
    stmt = select(Detection).where(
        Detection.inspection_id == inspection_id, Detection.frame_id == frame_id
    )
    if min_confidence is not None:
        stmt = stmt.where(Detection.confidence >= min_confidence)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Detection.created_at.asc(), Detection.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PaginatedDetectionsResponse(
        items=[DetectionPublic.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )

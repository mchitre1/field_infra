"""HTTP handlers for inspection media ingestion (multipart and presigned S3)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.api.deps import DbSession, S3Client, SettingsDep, SQSClient
from app.models.alignment import Alignment
from app.models.change_event import ChangeEvent
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection, SourceType
from app.models.progression_metric import ProgressionMetric
from app.schemas.alignment import (
    AlignmentCompareResponse,
    AlignmentPairPublic,
    ChangeEventPublic,
    PaginatedAlignmentPairsResponse,
    PaginatedChangeEventsResponse,
)
from app.schemas.detections import DetectionPublic, PaginatedDetectionsResponse
from app.schemas.frames import FramePublic
from app.schemas.ingest import CompleteIngestRequest, InspectionPublic, PresignRequest, PresignResponse
from app.schemas.progression import (
    PaginatedProgressionMetricsResponse,
    ProgressionMetricPublic,
    ProgressionMetricSummaryItem,
    ProgressionSummaryResponse,
)
from app.schemas.temporal_insights import ChangeMapResponse, TimelineEntry, TrendSummaryResponse
from app.services import anomaly_timeline as anomaly_timeline_service
from app.services import change_map as change_map_service
from app.services import ingest as ingest_service
from app.services import trend_summary as trend_summary_service

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


@router.get(
    "/ingest/{inspection_id}/alignment",
    response_model=PaginatedAlignmentPairsResponse,
)
def list_alignment_pairs(
    inspection_id: UUID,
    db: DbSession,
    asset_zone_id: str | None = None,
    change_type: str | None = None,
    detection_type: DetectionType | None = None,
    class_name: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedAlignmentPairsResponse:
    """List alignment pairs for a target inspection, with asset zone/change filters."""
    stmt = select(Alignment).where(Alignment.target_inspection_id == inspection_id)
    if asset_zone_id is not None:
        stmt = stmt.where(Alignment.asset_zone_id == asset_zone_id)
    if change_type is not None:
        stmt = stmt.where(Alignment.change_type == change_type)
    if class_name is not None:
        cn = class_name.strip().lower()
        bd = aliased(Detection)
        td = aliased(Detection)
        stmt = stmt.where(
            or_(
                select(1)
                .select_from(bd)
                .where(bd.id == Alignment.baseline_detection_id, func.lower(bd.class_name) == cn)
                .exists(),
                select(1)
                .select_from(td)
                .where(td.id == Alignment.target_detection_id, func.lower(td.class_name) == cn)
                .exists(),
            )
        )
    if detection_type is not None:
        bd2 = aliased(Detection)
        td2 = aliased(Detection)
        stmt = stmt.where(
            or_(
                select(1)
                .select_from(bd2)
                .where(
                    bd2.id == Alignment.baseline_detection_id,
                    bd2.detection_type == detection_type,
                )
                .exists(),
                select(1)
                .select_from(td2)
                .where(
                    td2.id == Alignment.target_detection_id,
                    td2.detection_type == detection_type,
                )
                .exists(),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Alignment.created_at.asc(), Alignment.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PaginatedAlignmentPairsResponse(
        items=[AlignmentPairPublic.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/ingest/{inspection_id}/progression/summary",
    response_model=ProgressionSummaryResponse,
)
def summarize_progression_metrics(
    inspection_id: UUID,
    db: DbSession,
) -> ProgressionSummaryResponse:
    """Aggregate min/max/latest progression metric values per metric_name for an inspection."""
    if db.get(Inspection, inspection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    rows = db.scalars(
        select(ProgressionMetric)
        .where(ProgressionMetric.target_inspection_id == inspection_id)
        .order_by(ProgressionMetric.created_at.asc(), ProgressionMetric.id.asc())
    ).all()
    by_name: dict[str, list[ProgressionMetric]] = {}
    for r in rows:
        by_name.setdefault(r.metric_name, []).append(r)
    items: list[ProgressionMetricSummaryItem] = []
    for name, group in sorted(by_name.items()):
        vals = [float(x.value) for x in group]
        latest = float(group[-1].value)
        items.append(
            ProgressionMetricSummaryItem(
                metric_name=name,
                min_value=min(vals),
                max_value=max(vals),
                latest_value=latest,
                count=len(group),
            )
        )
    return ProgressionSummaryResponse(target_inspection_id=inspection_id, items=items)


@router.get(
    "/ingest/{inspection_id}/progression",
    response_model=PaginatedProgressionMetricsResponse,
)
def list_progression_metrics(
    inspection_id: UUID,
    db: DbSession,
    metric_name: str | None = None,
    asset_zone_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedProgressionMetricsResponse:
    """List progression metrics for a target inspection (filters: metric_name, asset_zone_id)."""
    if db.get(Inspection, inspection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    stmt = select(ProgressionMetric).where(ProgressionMetric.target_inspection_id == inspection_id)
    if metric_name is not None:
        stmt = stmt.where(ProgressionMetric.metric_name == metric_name.strip())
    if asset_zone_id is not None:
        stmt = stmt.where(ProgressionMetric.asset_zone_id == asset_zone_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(
            ProgressionMetric.asset_zone_id.asc(),
            ProgressionMetric.metric_name.asc(),
            ProgressionMetric.created_at.asc(),
            ProgressionMetric.id.asc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return PaginatedProgressionMetricsResponse(
        items=[ProgressionMetricPublic.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/ingest/{inspection_id}/changes",
    response_model=PaginatedChangeEventsResponse,
)
def list_change_events(
    inspection_id: UUID,
    db: DbSession,
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedChangeEventsResponse:
    """List change events generated for an inspection."""
    stmt = select(ChangeEvent).where(ChangeEvent.inspection_id == inspection_id)
    if event_type is not None:
        stmt = stmt.where(ChangeEvent.event_type == event_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ChangeEvent.created_at.asc(), ChangeEvent.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PaginatedChangeEventsResponse(
        items=[ChangeEventPublic.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/ingest/compare/change-map", response_model=ChangeMapResponse)
def compare_change_map(
    baseline_inspection_id: UUID,
    target_inspection_id: UUID,
    settings: SettingsDep,
    db: DbSession,
    s3_client: S3Client,
    asset_zone_id: str | None = None,
    frame_id: UUID | None = None,
    include_frame_urls: bool = Query(default=False),
):
    """Normalized (0–1) bbox features per alignment side for baseline vs target overlay."""
    try:
        return change_map_service.build_change_map(
            settings=settings,
            db=db,
            s3_client=s3_client,
            baseline_inspection_id=baseline_inspection_id,
            target_inspection_id=target_inspection_id,
            asset_zone_id=asset_zone_id,
            frame_id=frame_id,
            include_frame_urls=include_frame_urls,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found") from None


@router.get("/ingest/timeline", response_model=list[TimelineEntry])
def list_timeline(
    settings: SettingsDep,
    db: DbSession,
    asset_zone_id: str = Query(..., min_length=1),
    org_id: UUID | None = None,
    site_hint: str | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    event_type: str | None = None,
    metric_name: str | None = None,
) -> list[TimelineEntry]:
    """Unified change events and progression metrics ordered by effective inspection time."""
    return anomaly_timeline_service.build_timeline(
        settings=settings,
        db=db,
        asset_zone_id=asset_zone_id.strip(),
        org_id=org_id,
        site_hint=site_hint.strip() if site_hint else None,
        effective_from=effective_from,
        effective_to=effective_to,
        event_type=event_type,
        metric_name=metric_name,
    )


@router.get("/ingest/trends", response_model=TrendSummaryResponse)
def get_trend_summary(
    settings: SettingsDep,
    db: DbSession,
    asset_zone_id: str = Query(..., min_length=1),
    metric_name: str = Query(..., min_length=1),
    org_id: UUID | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> TrendSummaryResponse:
    """Progression metric series and aggregates for one asset zone across target inspections."""
    return trend_summary_service.build_trend_summary(
        settings=settings,
        db=db,
        asset_zone_id=asset_zone_id.strip(),
        metric_name=metric_name.strip(),
        org_id=org_id,
        effective_from=effective_from,
        effective_to=effective_to,
    )


@router.get("/ingest/compare/alignment", response_model=AlignmentCompareResponse)
def compare_alignment_pairs(
    baseline_inspection_id: UUID,
    target_inspection_id: UUID,
    db: DbSession,
    asset_zone_id: str | None = None,
    change_type: str | None = None,
    detection_type: DetectionType | None = None,
    class_name: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> AlignmentCompareResponse:
    """Pairwise alignment rows for a baseline vs target inspection (read-only)."""
    if (
        db.get(Inspection, baseline_inspection_id) is None
        or db.get(Inspection, target_inspection_id) is None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    stmt = select(Alignment).where(
        Alignment.baseline_inspection_id == baseline_inspection_id,
        Alignment.target_inspection_id == target_inspection_id,
    )
    if asset_zone_id is not None:
        stmt = stmt.where(Alignment.asset_zone_id == asset_zone_id)
    if change_type is not None:
        stmt = stmt.where(Alignment.change_type == change_type)
    if class_name is not None:
        cn = class_name.strip().lower()
        bd = aliased(Detection)
        td = aliased(Detection)
        stmt = stmt.where(
            or_(
                select(1)
                .select_from(bd)
                .where(bd.id == Alignment.baseline_detection_id, func.lower(bd.class_name) == cn)
                .exists(),
                select(1)
                .select_from(td)
                .where(td.id == Alignment.target_detection_id, func.lower(td.class_name) == cn)
                .exists(),
            )
        )
    if detection_type is not None:
        bd2 = aliased(Detection)
        td2 = aliased(Detection)
        stmt = stmt.where(
            or_(
                select(1)
                .select_from(bd2)
                .where(
                    bd2.id == Alignment.baseline_detection_id,
                    bd2.detection_type == detection_type,
                )
                .exists(),
                select(1)
                .select_from(td2)
                .where(
                    td2.id == Alignment.target_detection_id,
                    td2.detection_type == detection_type,
                )
                .exists(),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Alignment.created_at.asc(), Alignment.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AlignmentCompareResponse(
        baseline_inspection_id=baseline_inspection_id,
        target_inspection_id=target_inspection_id,
        items=[AlignmentPairPublic.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )

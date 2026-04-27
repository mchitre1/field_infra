import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.jobs.messages import IngestJobMessage
from app.models.inspection import Inspection, InspectionStatus
from app.services.inspection_history_service import record_inspection_status_transition

log = logging.getLogger(__name__)


def publish_ingest_job(
    *,
    settings: Settings,
    db: Session,
    inspection: Inspection,
    sqs_client: Any,
) -> bool:
    """
    After S3 + DB persist, notify the processing pipeline.
    If SQS is not configured (empty URL), status remains ``stored``.
    On publish failure after a successful store, sets ``stored_pending_queue`` and
    records ``last_queue_error`` for retry (see plan algorithms).
    """
    if not settings.sqs_queue_url:
        log.warning("SQS_QUEUE_URL unset; skipping enqueue for inspection %s", inspection.id)
        return True

    msg = IngestJobMessage(
        inspection_id=inspection.id,
        s3_uri=f"s3://{inspection.s3_bucket}/{inspection.s3_key}",
        content_type=inspection.content_type,
        source_type=inspection.source_type,
        capture_timestamp=inspection.capture_timestamp,
        site_hint=inspection.site_hint,
        asset_hint=inspection.asset_hint,
        frame_extraction={
            "mode": "default",
            "fps": settings.frame_extraction_fps,
            "max_frames": settings.max_frames_per_inspection,
            "frames_bucket": settings.frames_bucket or settings.s3_bucket,
        },
        detection={
            "mode": "default",
            "threshold": settings.inference_confidence_threshold,
            "model_name": settings.inference_model_name,
            "model_version": settings.inference_model_version,
            "enabled_classes": [],
        },
    )
    try:
        sqs_client.send_message(
            QueueUrl=settings.sqs_queue_url,
            MessageBody=msg.model_dump_json(),
        )
    except Exception as e:
        prev_status = inspection.status
        inspection.status = InspectionStatus.stored_pending_queue
        inspection.last_queue_error = str(e)
        db.add(inspection)
        record_inspection_status_transition(
            db=db,
            inspection_id=inspection.id,
            from_status=prev_status,
            to_status=InspectionStatus.stored_pending_queue,
            source="api",
            context={"stage": "sqs_publish", "error": str(e)[:500]},
        )
        db.commit()
        log.exception("SQS publish failed for inspection %s", inspection.id)
        return False

    prev_status = inspection.status
    inspection.status = InspectionStatus.queued
    inspection.last_queue_error = None
    db.add(inspection)
    record_inspection_status_transition(
        db=db,
        inspection_id=inspection.id,
        from_status=prev_status,
        to_status=InspectionStatus.queued,
        source="api",
        context={"stage": "sqs_publish"},
    )
    db.commit()
    return True

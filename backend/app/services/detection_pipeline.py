from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.detection import Detection
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus
from app.services import storage
from app.services.detection_inference import run_frame_detection


def run_detection_for_inspection(
    *,
    settings: Settings,
    db: Session,
    s3_client: Any,
    inspection_id: uuid.UUID,
    detection_hints: dict[str, Any] | None = None,
) -> int:
    """Run detection over all extracted frames for one inspection.

    Existing detection rows for the inspection are replaced on each run. On success
    updates `detection_count` and marks `detections_ready`; on failure marks
    `detections_failed` and stores error detail in inspection metadata.
    """
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise ValueError(f"Inspection {inspection_id} not found")

    inspection.status = InspectionStatus.processing_detections
    db.add(inspection)
    db.commit()

    try:
        frames = db.scalars(
            select(Frame)
            .where(Frame.inspection_id == inspection.id)
            .order_by(Frame.frame_index.asc())
        ).all()
        db.execute(delete(Detection).where(Detection.inspection_id == inspection.id))

        threshold = None
        hints = detection_hints or {}
        if "threshold" in hints:
            threshold = float(hints["threshold"])
        model_name = str(hints.get("model_name", settings.inference_model_name))
        model_version = str(hints.get("model_version", settings.inference_model_version))
        enabled_classes: set[str] | None = None
        raw_enabled = hints.get("enabled_classes")
        if isinstance(raw_enabled, (list, tuple, set)):
            normalized = {str(v).strip().lower() for v in raw_enabled if str(v).strip()}
            enabled_classes = normalized or None

        count = 0
        for frame in frames:
            frame_bytes = storage.get_object_bytes(
                s3_client=s3_client, bucket=frame.s3_bucket, key=frame.s3_key
            )
            detections = run_frame_detection(
                settings=settings,
                frame_bytes=frame_bytes,
                threshold_override=threshold,
            )
            for det in detections:
                if enabled_classes is not None and det.class_name.lower() not in enabled_classes:
                    continue
                db.add(
                    Detection(
                        id=uuid.uuid4(),
                        inspection_id=inspection.id,
                        frame_id=frame.id,
                        detection_type=det.detection_type,
                        class_name=det.class_name,
                        confidence=det.confidence,
                        bbox_xmin=det.bbox_xmin,
                        bbox_ymin=det.bbox_ymin,
                        bbox_xmax=det.bbox_xmax,
                        bbox_ymax=det.bbox_ymax,
                        geometry=det.geometry,
                        model_name=model_name,
                        model_version=model_version,
                        extra_attributes=det.attributes,
                    )
                )
                count += 1

        inspection.detection_count = count
        inspection.status = InspectionStatus.detections_ready
        metadata = dict(inspection.extra_metadata or {})
        metadata.pop("detection_error", None)
        inspection.extra_metadata = metadata or None
        db.add(inspection)
        db.commit()
        return count
    except Exception as exc:
        db.rollback()
        inspection = db.get(Inspection, inspection_id)
        if inspection is not None:
            inspection.status = InspectionStatus.detections_failed
            metadata = dict(inspection.extra_metadata or {})
            metadata["detection_error"] = str(exc)
            inspection.extra_metadata = metadata
            db.add(inspection)
            db.commit()
        raise

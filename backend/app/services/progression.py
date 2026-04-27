from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.alignment import Alignment
from app.models.detection import Detection, DetectionType
from app.models.inspection import Inspection, InspectionStatus
from app.models.progression_metric import ProgressionMetric
from app.services.class_taxonomy import CRACK_CLASSES, VEGETATION_ENCROACHMENT_CLASSES
from app.services.progression_crack import build_crack_metric_drafts
from app.services.progression_vegetation import build_vegetation_metric_drafts


def _record_progression_error(db: Session, inspection_id: uuid.UUID, message: str) -> None:
    ins = db.get(Inspection, inspection_id)
    if ins is None:
        return
    meta = dict(ins.extra_metadata or {})
    meta["progression_error"] = message
    ins.extra_metadata = meta
    ins.progression_metric_count = 0
    db.add(ins)
    db.commit()


def run_progression_for_inspection(
    *,
    settings: Settings,
    db: Session,
    inspection_id: uuid.UUID,
) -> int:
    """Derive progression metrics from persisted alignment pairs for a target inspection.

    Replaces all existing ``ProgressionMetric`` rows for this target. Intended to run
    after alignment succeeds (``alignment_ready``).

    On failure, records ``progression_error`` in inspection metadata and returns 0.
    """
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise ValueError(f"Inspection {inspection_id} not found")

    if inspection.status != InspectionStatus.alignment_ready:
        return 0

    min_dt = float(settings.progression_min_time_delta_seconds)

    try:
        db.execute(
            delete(ProgressionMetric).where(ProgressionMetric.target_inspection_id == inspection.id)
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _record_progression_error(db, inspection_id, str(exc))
        return 0

    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        return 0

    if inspection.status != InspectionStatus.alignment_ready:
        return 0

    try:
        stmt = (
            select(Alignment)
            .where(
                Alignment.target_inspection_id == inspection.id,
                Alignment.change_type == "persisted",
                Alignment.baseline_detection_id.is_not(None),
                Alignment.target_detection_id.is_not(None),
            )
            .order_by(Alignment.created_at.asc(), Alignment.id.asc())
        )
        pairs = db.scalars(stmt).all()
        written = 0

        for ap in pairs:
            bd_id = ap.baseline_detection_id
            td_id = ap.target_detection_id
            if bd_id is None or td_id is None:
                continue
            bd = db.get(Detection, bd_id)
            td = db.get(Detection, td_id)
            bi = db.get(Inspection, ap.baseline_inspection_id)
            ti = db.get(Inspection, ap.target_inspection_id)
            if bd is None or td is None or bi is None or ti is None:
                continue

            drafts: list[Any] = []
            cn = td.class_name.strip().lower()

            if (
                td.detection_type == DetectionType.defect
                and cn in CRACK_CLASSES
                and bd.detection_type == DetectionType.defect
                and bd.class_name.strip().lower() in CRACK_CLASSES
            ):
                drafts.extend(
                    build_crack_metric_drafts(
                        baseline=bd,
                        target=td,
                        baseline_inspection=bi,
                        target_inspection=ti,
                        crack_metric=settings.progression_crack_metric,
                        min_time_delta_seconds=min_dt,
                    )
                )
            elif (
                td.detection_type == DetectionType.environmental_hazard
                and cn in VEGETATION_ENCROACHMENT_CLASSES
                and bd.detection_type == DetectionType.environmental_hazard
                and bd.class_name.strip().lower() in VEGETATION_ENCROACHMENT_CLASSES
            ):
                drafts.extend(
                    build_vegetation_metric_drafts(
                        baseline=bd,
                        target=td,
                        baseline_inspection=bi,
                        target_inspection=ti,
                        vegetation_metric=settings.progression_vegetation_metric,
                        min_time_delta_seconds=min_dt,
                    )
                )
            else:
                continue

            for d in drafts:
                db.add(
                    ProgressionMetric(
                        id=uuid.uuid4(),
                        asset_zone_id=ap.asset_zone_id,
                        baseline_inspection_id=ap.baseline_inspection_id,
                        target_inspection_id=ap.target_inspection_id,
                        alignment_pair_id=ap.id,
                        metric_name=d.metric_name,
                        metric_unit=d.metric_unit,
                        value=d.value,
                        payload=d.payload,
                    )
                )
                written += 1

        inspection.progression_metric_count = written
        meta = dict(inspection.extra_metadata or {})
        meta.pop("progression_error", None)
        inspection.extra_metadata = meta or None
        db.add(inspection)
        db.commit()
        return written
    except Exception as exc:
        db.rollback()
        _record_progression_error(db, inspection_id, str(exc))
        return 0

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.alignment import Alignment
from app.models.detection import Detection
from app.models.inspection import Inspection, InspectionStatus
from app.services.alignment_matching import match_detection_sets
from app.services.asset_zone import build_asset_zone_id
from app.services.change_detection import build_change_events
from app.services.geo import haversine_meters


def _ref_time(ins: Inspection):
    """Comparable instant for ordering and cohort gating (capture preferred)."""
    if ins.capture_timestamp is not None:
        return ins.capture_timestamp
    return ins.created_at


def _within_geo(a: Inspection, b: Inspection, max_m: float) -> bool:
    if (
        a.latitude is None
        or a.longitude is None
        or b.latitude is None
        or b.longitude is None
    ):
        return True
    return (
        haversine_meters(float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude))
        <= max_m
    )


def _select_baseline_inspection(
    db: Session, inspection: Inspection, settings: Settings
) -> Inspection | None:
    """Pick the most recent *prior* inspection in the same cohort within time/geo tolerance."""
    stmt = (
        select(Inspection)
        .where(
            Inspection.id != inspection.id,
            Inspection.status.in_(
                [InspectionStatus.detections_ready, InspectionStatus.alignment_ready]
            ),
            Inspection.org_id == inspection.org_id,
            Inspection.site_hint == inspection.site_hint,
            Inspection.asset_hint == inspection.asset_hint,
        )
    )
    candidates = db.scalars(stmt).all()
    if not candidates:
        return None
    target_ref = _ref_time(inspection)
    tol = timedelta(seconds=settings.alignment_time_tolerance_seconds)
    priors: list[Inspection] = []
    for c in candidates:
        cref = _ref_time(c)
        if cref >= target_ref:
            continue
        delta = target_ref - cref
        if delta > tol:
            continue
        if not _within_geo(c, inspection, settings.alignment_geo_tolerance_meters):
            continue
        priors.append(c)
    if not priors:
        return None
    priors.sort(key=lambda x: _ref_time(x), reverse=True)
    return priors[0]


def run_alignment_for_inspection(
    *,
    settings: Settings,
    db: Session,
    inspection_id: uuid.UUID,
) -> tuple[int, int]:
    """Align target inspection detections against a selected baseline inspection.

    Returns ``(aligned_pair_count, change_event_count)``. Existing alignment/change
    rows for the target inspection are replaced on rerun.
    """
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise ValueError(f"Inspection {inspection_id} not found")
    inspection.status = InspectionStatus.processing_alignment
    db.add(inspection)
    db.commit()
    try:
        baseline = _select_baseline_inspection(db, inspection, settings)
        db.execute(delete(Alignment).where(Alignment.target_inspection_id == inspection.id))
        from app.models.change_event import ChangeEvent

        db.execute(delete(ChangeEvent).where(ChangeEvent.inspection_id == inspection.id))
        if baseline is None:
            inspection.aligned_pair_count = 0
            inspection.change_event_count = 0
            inspection.status = InspectionStatus.alignment_ready
            db.add(inspection)
            db.commit()
            return 0, 0

        baseline_dets = db.scalars(
            select(Detection).where(Detection.inspection_id == baseline.id)
        ).all()
        target_dets = db.scalars(
            select(Detection).where(Detection.inspection_id == inspection.id)
        ).all()
        by_zone_base: dict[str, list[Detection]] = defaultdict(list)
        by_zone_target: dict[str, list[Detection]] = defaultdict(list)
        for d in baseline_dets:
            by_zone_base[build_asset_zone_id(d, inspection=baseline)].append(d)
        for d in target_dets:
            by_zone_target[build_asset_zone_id(d, inspection=inspection)].append(d)

        all_zones = sorted(set(by_zone_base) | set(by_zone_target))
        pair_count = 0
        event_count = 0
        for zone in all_zones:
            pairs = match_detection_sets(
                by_zone_base.get(zone, []),
                by_zone_target.get(zone, []),
                iou_threshold=settings.alignment_iou_threshold,
                min_confidence=settings.alignment_min_confidence,
                max_centroid_norm_distance=settings.alignment_max_centroid_norm_distance,
            )
            for p in pairs:
                db.add(
                    Alignment(
                        id=uuid.uuid4(),
                        asset_zone_id=zone,
                        baseline_inspection_id=baseline.id,
                        target_inspection_id=inspection.id,
                        baseline_detection_id=p.baseline.id if p.baseline else None,
                        target_detection_id=p.target.id if p.target else None,
                        alignment_score=p.score,
                        change_type=p.change_type,
                    )
                )
                pair_count += 1
            for ev in build_change_events(
                inspection_id=inspection.id, asset_zone_id=zone, pairs=pairs
            ):
                db.add(ev)
                event_count += 1

        inspection.aligned_pair_count = pair_count
        inspection.change_event_count = event_count
        inspection.status = InspectionStatus.alignment_ready
        metadata = dict(inspection.extra_metadata or {})
        metadata.pop("alignment_error", None)
        inspection.extra_metadata = metadata or None
        db.add(inspection)
        db.commit()
        return pair_count, event_count
    except Exception as exc:
        db.rollback()
        inspection = db.get(Inspection, inspection_id)
        if inspection is not None:
            inspection.status = InspectionStatus.alignment_failed
            metadata = dict(inspection.extra_metadata or {})
            metadata["alignment_error"] = str(exc)
            inspection.extra_metadata = metadata
            db.add(inspection)
            db.commit()
        raise

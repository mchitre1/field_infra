"""Persist prioritized maintenance recommendations for a target inspection."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.alignment import Alignment
from app.models.change_event import ChangeEvent
from app.models.detection import Detection
from app.models.inspection import Inspection, InspectionStatus
from app.models.maintenance_recommendation import MaintenanceRecommendation
from app.models.progression_metric import ProgressionMetric
from app.services.asset_zone import build_asset_zone_id
from app.services.recommendation_rules import (
    priority_label_for_score,
    score_zone,
    sla_days_for_label,
)

log = logging.getLogger(__name__)


def _effective_time(ins: Inspection) -> datetime:
    t = ins.capture_timestamp or ins.created_at
    if t.tzinfo is None:
        return t.replace(tzinfo=timezone.utc)
    return t


def _record_recommendation_error(db: Session, inspection_id: uuid.UUID, message: str) -> None:
    ins = db.get(Inspection, inspection_id)
    if ins is None:
        return
    meta = dict(ins.extra_metadata or {})
    meta["recommendation_error"] = message
    ins.extra_metadata = meta
    ins.recommendation_count = 0
    db.add(ins)
    db.commit()


def run_recommendations_for_inspection(
    *,
    settings: Settings,
    db: Session,
    inspection_id: uuid.UUID,
) -> int:
    """Replace recommendations for ``inspection_id``. Returns row count written.

    Runs only when inspection status is ``alignment_ready`` (otherwise returns ``0``
    without writing). Deletes existing rows for the target, scores each asset zone,
    sorts by score, and persists at most ``recommend_max_per_inspection`` rows.
    Clears ``metadata.recommendation_error`` on success.
    """
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise ValueError(f"Inspection {inspection_id} not found")

    if inspection.status != InspectionStatus.alignment_ready:
        return 0

    try:
        db.execute(
            delete(MaintenanceRecommendation).where(
                MaintenanceRecommendation.target_inspection_id == inspection.id
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _record_recommendation_error(db, inspection_id, str(exc))
        return 0

    inspection = db.get(Inspection, inspection_id)
    if inspection is None or inspection.status != InspectionStatus.alignment_ready:
        return 0

    detections = db.scalars(
        select(Detection).where(Detection.inspection_id == inspection.id).order_by(Detection.id.asc())
    ).all()
    by_zone: dict[str, list[Detection]] = {}
    for d in detections:
        z = build_asset_zone_id(d, inspection=inspection)
        by_zone.setdefault(z, []).append(d)

    change_events = db.scalars(
        select(ChangeEvent)
        .where(ChangeEvent.inspection_id == inspection.id)
        .order_by(ChangeEvent.created_at.asc(), ChangeEvent.id.asc())
    ).all()
    ce_by_zone: dict[str, list[ChangeEvent]] = {}
    for ev in change_events:
        ce_by_zone.setdefault(ev.asset_zone_id, []).append(ev)

    alignments = db.scalars(
        select(Alignment)
        .where(Alignment.target_inspection_id == inspection.id)
        .order_by(Alignment.created_at.asc(), Alignment.id.asc())
    ).all()
    al_by_zone: dict[str, list[Alignment]] = {}
    for a in alignments:
        al_by_zone.setdefault(a.asset_zone_id, []).append(a)

    pm_rows = db.scalars(
        select(ProgressionMetric)
        .where(ProgressionMetric.target_inspection_id == inspection.id)
        .order_by(ProgressionMetric.created_at.asc(), ProgressionMetric.id.asc())
    ).all()
    pm_by_zone: dict[str, list[ProgressionMetric]] = {}
    for pm in pm_rows:
        pm_by_zone.setdefault(pm.asset_zone_id, []).append(pm)

    zone_keys: set[str] = (
        set(by_zone) | set(ce_by_zone) | set(al_by_zone) | set(pm_by_zone)
    )

    if not zone_keys:
        meta = dict(inspection.extra_metadata or {})
        meta.pop("recommendation_error", None)
        inspection.extra_metadata = meta or None
        inspection.recommendation_count = 0
        db.add(inspection)
        db.commit()
        return 0

    scored: list[tuple[str, float, list[dict[str, Any]], str]] = []
    for z in sorted(zone_keys):
        dets = by_zone.get(z, [])
        evs = ce_by_zone.get(z, [])
        pms = pm_by_zone.get(z, [])
        s, factors, summary = score_zone(
            settings=settings,
            zone_id=z,
            detections=dets,
            change_events=evs,
            progression_metrics=pms,
        )
        al_n = len(al_by_zone.get(z, []))
        if not factors and not dets and not evs and not pms and al_n == 0:
            continue
        if not factors and al_n > 0 and not dets and not evs and not pms:
            s = max(s, 1.0)
            factors = [
                {
                    "kind": "alignment",
                    "message": f"{al_n} alignment pair(s) for this zone on the target inspection",
                    "refs": {"zone_id": z, "alignment_pair_count": al_n},
                }
            ]
            summary = f"Review zone {z}"
        if not factors and dets:
            s = max(s, 1.0)
            factors = [
                {
                    "kind": "detection",
                    "message": "Defect or hazard observations present; schedule follow-up inspection",
                    "refs": {"zone_id": z},
                }
            ]
            summary = f"Review zone {z}"
        scored.append((z, s, factors, summary))

    scored.sort(key=lambda row: (-row[1], row[0]))
    lim = settings.recommend_max_per_inspection
    truncated = scored[lim:]
    scored = scored[:lim]

    t_eff = _effective_time(inspection)
    n_written = 0
    try:
        for rank, (zone_id, pscore, rationale, action_summary) in enumerate(scored, start=1):
            label = priority_label_for_score(settings=settings, score=pscore)
            days = sla_days_for_label(settings=settings, label=label)
            sla_at = t_eff + timedelta(seconds=days * 86400.0)
            db.add(
                MaintenanceRecommendation(
                    id=uuid.uuid4(),
                    target_inspection_id=inspection.id,
                    asset_zone_id=zone_id,
                    priority_rank=rank,
                    priority_label=label,
                    priority_score=pscore,
                    action_summary=action_summary[:512],
                    rationale=rationale
                    or [
                        {
                            "kind": "baseline",
                            "message": "Zone included from alignment or change tracking with neutral score",
                            "refs": {"zone_id": zone_id},
                        }
                    ],
                    sla_target_at=sla_at,
                    sla_days_suggested=days,
                )
            )
            n_written += 1
        if truncated:
            log.info(
                "Recommendations truncated for inspection %s: %s zones dropped over max_per_inspection=%s",
                inspection.id,
                len(truncated),
                lim,
            )
        meta = dict(inspection.extra_metadata or {})
        meta.pop("recommendation_error", None)
        inspection.extra_metadata = meta or None
        inspection.recommendation_count = n_written
        db.add(inspection)
        db.commit()
    except Exception as exc:
        db.rollback()
        _record_recommendation_error(db, inspection_id, str(exc))
        return 0

    return n_written

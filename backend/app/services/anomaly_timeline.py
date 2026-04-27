"""Merge change events and progression metrics into a single time-ordered timeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.change_event import ChangeEvent
from app.models.inspection import Inspection
from app.models.progression_metric import ProgressionMetric
from app.schemas.temporal_insights import TimelineEntry


def _effective_at(ins: Inspection) -> datetime:
    return ins.capture_timestamp or ins.created_at


def _severity_from_payload(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    v = payload.get("severity")
    if isinstance(v, (int, float)):
        return float(v)
    return None


def build_timeline(
    *,
    settings: Settings,
    db: Session,
    asset_zone_id: str,
    org_id: uuid.UUID | None,
    site_hint: str | None,
    effective_from: datetime | None,
    effective_to: datetime | None,
    event_type: str | None,
    metric_name: str | None,
) -> list[TimelineEntry]:
    """Merge change events and progression metrics, sorted by effective inspection time.

    Each source query is capped before merge; if the merged list exceeds
    ``timeline_max_entries``, the oldest rows are dropped (newest slice kept).
    """
    cap = max(settings.timeline_max_entries, 1) * 5
    cap = min(cap, 50_000)

    insp = Inspection
    eff_ce = func.coalesce(insp.capture_timestamp, insp.created_at)

    ce_stmt = (
        select(ChangeEvent, insp)
        .join(insp, ChangeEvent.inspection_id == insp.id)
        .where(ChangeEvent.asset_zone_id == asset_zone_id)
    )
    if org_id is not None:
        ce_stmt = ce_stmt.where(insp.org_id == org_id)
    if site_hint is not None:
        ce_stmt = ce_stmt.where(insp.site_hint == site_hint)
    if effective_from is not None:
        ce_stmt = ce_stmt.where(eff_ce >= effective_from)
    if effective_to is not None:
        ce_stmt = ce_stmt.where(eff_ce <= effective_to)
    if event_type is not None:
        ce_stmt = ce_stmt.where(ChangeEvent.event_type == event_type.strip())

    ce_stmt = ce_stmt.order_by(eff_ce.desc(), ChangeEvent.inspection_id.asc(), ChangeEvent.id.asc()).limit(cap)
    ce_rows = list(db.execute(ce_stmt).all())

    insp2 = Inspection
    eff_pm = func.coalesce(insp2.capture_timestamp, insp2.created_at)

    pm_stmt = (
        select(ProgressionMetric, insp2)
        .join(insp2, ProgressionMetric.target_inspection_id == insp2.id)
        .where(ProgressionMetric.asset_zone_id == asset_zone_id)
    )
    if org_id is not None:
        pm_stmt = pm_stmt.where(insp2.org_id == org_id)
    if site_hint is not None:
        pm_stmt = pm_stmt.where(insp2.site_hint == site_hint)
    if effective_from is not None:
        pm_stmt = pm_stmt.where(eff_pm >= effective_from)
    if effective_to is not None:
        pm_stmt = pm_stmt.where(eff_pm <= effective_to)
    if metric_name is not None:
        pm_stmt = pm_stmt.where(ProgressionMetric.metric_name == metric_name.strip())

    pm_stmt = pm_stmt.order_by(eff_pm.desc(), ProgressionMetric.target_inspection_id.asc(), ProgressionMetric.id.asc()).limit(cap)
    pm_rows = list(db.execute(pm_stmt).all())

    merged: list[tuple[datetime, uuid.UUID, uuid.UUID, int, TimelineEntry]] = []
    for ev, ins_row in ce_rows:
        eff = _effective_at(ins_row)
        pl = ev.event_payload or {}
        summary = f"Change {ev.event_type}"
        if isinstance(pl, dict) and pl.get("class_name"):
            summary += f" ({pl.get('class_name')})"
        entry = TimelineEntry(
            entry_kind="change_event",
            effective_at=eff,
            inspection_id=ev.inspection_id,
            asset_zone_id=ev.asset_zone_id,
            severity=_severity_from_payload(pl if isinstance(pl, dict) else None),
            summary=summary,
            refs={
                "change_event_id": str(ev.id),
                "event_type": ev.event_type,
                "payload": pl if isinstance(pl, dict) else {},
            },
        )
        merged.append((eff, ev.inspection_id, ev.id, 0, entry))

    for pm, ins_row in pm_rows:
        eff = _effective_at(ins_row)
        summary = f"Progression {pm.metric_name}={pm.value:g} {pm.metric_unit}"
        payload = pm.payload if isinstance(pm.payload, dict) else {}
        entry = TimelineEntry(
            entry_kind="progression_metric",
            effective_at=eff,
            inspection_id=pm.target_inspection_id,
            asset_zone_id=pm.asset_zone_id,
            severity=None,
            summary=summary,
            refs={
                "progression_metric_id": str(pm.id),
                "metric_name": pm.metric_name,
                "baseline_inspection_id": str(pm.baseline_inspection_id),
                "target_inspection_id": str(pm.target_inspection_id),
                "value": pm.value,
                "metric_unit": pm.metric_unit,
                "payload": payload,
            },
        )
        merged.append((eff, pm.target_inspection_id, pm.id, 1, entry))

    merged.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    lim = settings.timeline_max_entries
    if len(merged) > lim:
        merged = merged[-lim:]

    return [t[4] for t in merged]

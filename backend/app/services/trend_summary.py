"""Cross-inspection progression trends for one asset zone and metric."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.inspection import Inspection
from app.models.progression_metric import ProgressionMetric
from app.schemas.temporal_insights import TrendSeriesPoint, TrendSummaryResponse


def _effective_at(ins: Inspection) -> datetime:
    return ins.capture_timestamp or ins.created_at


def _filtered_pm_query(*, asset_zone_id: str, metric_name: str) -> tuple[Select, list]:
    insp = Inspection
    filters = [
        ProgressionMetric.asset_zone_id == asset_zone_id,
        ProgressionMetric.metric_name == metric_name,
    ]
    base: Select = (
        select(ProgressionMetric, insp)
        .join(insp, ProgressionMetric.target_inspection_id == insp.id)
        .where(*filters)
    )
    return base, filters


def build_trend_summary(
    *,
    settings: Settings,
    db: Session,
    asset_zone_id: str,
    metric_name: str,
    org_id: uuid.UUID | None,
    effective_from: datetime | None,
    effective_to: datetime | None,
) -> TrendSummaryResponse:
    """Progression samples and aggregates for one ``asset_zone_id`` and ``metric_name``.

    ``points`` may be a truncated recent window (``truncated``) while ``min``/``max``/``mean``
    reflect the full filtered series. ``delta_first_to_latest`` and ``simple_slope_per_day``
    use the chronologically first and last matching rows (not only the truncated slice).
    """
    insp = Inspection
    eff = func.coalesce(insp.capture_timestamp, insp.created_at)
    name = metric_name.strip()

    base, filters = _filtered_pm_query(asset_zone_id=asset_zone_id, metric_name=name)
    if org_id is not None:
        base = base.where(insp.org_id == org_id)
    if effective_from is not None:
        base = base.where(eff >= effective_from)
    if effective_to is not None:
        base = base.where(eff <= effective_to)

    count_stmt = (
        select(func.count())
        .select_from(ProgressionMetric)
        .join(insp, ProgressionMetric.target_inspection_id == insp.id)
        .where(*filters)
    )
    if org_id is not None:
        count_stmt = count_stmt.where(insp.org_id == org_id)
    if effective_from is not None:
        count_stmt = count_stmt.where(eff >= effective_from)
    if effective_to is not None:
        count_stmt = count_stmt.where(eff <= effective_to)
    total = db.scalar(count_stmt) or 0
    lim = settings.trend_max_points
    truncated = total > lim

    stmt = base.order_by(eff.desc(), ProgressionMetric.target_inspection_id.asc(), ProgressionMetric.id.desc()).limit(lim)
    rows = list(db.execute(stmt).all())
    rows.reverse()

    points: list[TrendSeriesPoint] = []
    for pm, ins_row in rows:
        points.append(
            TrendSeriesPoint(
                effective_at=_effective_at(ins_row),
                inspection_id=pm.target_inspection_id,
                value=float(pm.value),
                metric_unit=pm.metric_unit,
            )
        )

    if total == 0:
        return TrendSummaryResponse(
            asset_zone_id=asset_zone_id,
            metric_name=name,
            points=[],
            truncated=truncated,
        )

    agg_stmt = (
        select(
            func.min(ProgressionMetric.value),
            func.max(ProgressionMetric.value),
            func.avg(ProgressionMetric.value),
        )
        .select_from(ProgressionMetric)
        .join(insp, ProgressionMetric.target_inspection_id == insp.id)
        .where(*filters)
    )
    if org_id is not None:
        agg_stmt = agg_stmt.where(insp.org_id == org_id)
    if effective_from is not None:
        agg_stmt = agg_stmt.where(eff >= effective_from)
    if effective_to is not None:
        agg_stmt = agg_stmt.where(eff <= effective_to)
    min_v, max_v, mean_v = db.execute(agg_stmt).one()
    min_f = float(min_v)
    max_f = float(max_v)
    mean_f = float(mean_v)

    first_stmt = base.order_by(eff.asc(), ProgressionMetric.id.asc()).limit(1)
    last_stmt = base.order_by(eff.desc(), ProgressionMetric.id.desc()).limit(1)
    first_row = db.execute(first_stmt).one()
    last_row = db.execute(last_stmt).one()

    pm_first, ins_first = first_row
    pm_last, ins_last = last_row
    latest_f = float(pm_last.value)

    delta: float | None = None
    slope: float | None = None
    if total >= 2:
        delta = float(pm_last.value) - float(pm_first.value)
        t0 = _effective_at(ins_first)
        t1 = _effective_at(ins_last)
        span_sec = (t1 - t0).total_seconds()
        span_days = span_sec / 86400.0 if span_sec > 0 else 0.0
        if span_days >= settings.trend_min_span_days and span_days > 0:
            slope = delta / span_days

    return TrendSummaryResponse(
        asset_zone_id=asset_zone_id,
        metric_name=name,
        points=points,
        min_value=min_f,
        max_value=max_f,
        mean_value=mean_f,
        latest_value=latest_f,
        delta_first_to_latest=delta,
        simple_slope_per_day=slope,
        truncated=truncated,
    )

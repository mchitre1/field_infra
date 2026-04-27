import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.models.progression_metric import ProgressionMetric
from app.services.trend_summary import build_trend_summary


def _inspection(sqlite_session: Session, iid: uuid.UUID, cap: datetime | None) -> None:
    sqlite_session.add(
        Inspection(
            id=iid,
            org_id=None,
            source_type=SourceType.drone,
            site_hint=None,
            asset_hint=None,
            capture_timestamp=cap,
            s3_bucket="b",
            s3_key=str(iid),
            content_type="image/jpeg",
            byte_size=10,
            status=InspectionStatus.alignment_ready,
        )
    )
    sqlite_session.commit()


def test_trend_single_point(sqlite_session: Session):
    zone = "z-tr-1"
    base = uuid.UUID("11111111-1111-1111-1111-111111111111")
    tgt = uuid.UUID("22222222-2222-2222-2222-222222222222")
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _inspection(sqlite_session, base, t0)
    _inspection(sqlite_session, tgt, t0)
    sqlite_session.add(
        ProgressionMetric(
            id=uuid.uuid4(),
            asset_zone_id=zone,
            baseline_inspection_id=base,
            target_inspection_id=tgt,
            metric_name="m1",
            metric_unit="u",
            value=3.0,
            payload=None,
        )
    )
    sqlite_session.commit()

    out = build_trend_summary(
        settings=Settings(),
        db=sqlite_session,
        asset_zone_id=zone,
        metric_name="m1",
        org_id=None,
        effective_from=None,
        effective_to=None,
    )
    assert len(out.points) == 1
    assert out.min_value == 3.0 and out.max_value == 3.0 and out.mean_value == 3.0
    assert out.latest_value == 3.0
    assert out.delta_first_to_latest is None
    assert out.simple_slope_per_day is None


def test_trend_two_points_delta_and_slope(sqlite_session: Session):
    zone = "z-tr-2"
    b1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    t1 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    b2 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    t2 = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    day0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    day10 = day0 + timedelta(days=10)
    for iid, cap in ((b1, day0), (t1, day0), (b2, day0), (t2, day10)):
        _inspection(sqlite_session, iid, cap)

    sqlite_session.add_all(
        [
            ProgressionMetric(
                id=uuid.uuid4(),
                asset_zone_id=zone,
                baseline_inspection_id=b1,
                target_inspection_id=t1,
                metric_name="rate_metric",
                metric_unit="u",
                value=0.0,
                payload=None,
            ),
            ProgressionMetric(
                id=uuid.uuid4(),
                asset_zone_id=zone,
                baseline_inspection_id=b2,
                target_inspection_id=t2,
                metric_name="rate_metric",
                metric_unit="u",
                value=10.0,
                payload=None,
            ),
        ]
    )
    sqlite_session.commit()

    settings = Settings()
    settings.trend_min_span_days = 1.0
    out = build_trend_summary(
        settings=settings,
        db=sqlite_session,
        asset_zone_id=zone,
        metric_name="rate_metric",
        org_id=None,
        effective_from=None,
        effective_to=None,
    )
    assert len(out.points) == 2
    assert out.points[0].value == 0.0 and out.points[1].value == 10.0
    assert out.delta_first_to_latest == 10.0
    assert out.simple_slope_per_day is not None
    assert abs(out.simple_slope_per_day - 1.0) < 1e-6


def test_trend_truncated_points_keeps_global_aggregates(sqlite_session: Session):
    """min/max/mean and delta use full series; points[] is capped to trend_max_points."""
    zone = "z-tr-trunc"
    day0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    inspections: list[tuple[uuid.UUID, uuid.UUID, datetime, float]] = []
    for i in range(3):
        b = uuid.uuid4()
        t = uuid.uuid4()
        cap = day0 + timedelta(days=i)
        val = float(i * 5)  # 0, 5, 10
        inspections.append((b, t, cap, val))

    for b, t, cap, _ in inspections:
        _inspection(sqlite_session, b, cap)
        _inspection(sqlite_session, t, cap)

    for (b, t, _, val) in inspections:
        sqlite_session.add(
            ProgressionMetric(
                id=uuid.uuid4(),
                asset_zone_id=zone,
                baseline_inspection_id=b,
                target_inspection_id=t,
                metric_name="m_trunc",
                metric_unit="u",
                value=val,
                payload=None,
            )
        )
    sqlite_session.commit()

    settings = Settings()
    settings.trend_max_points = 2
    settings.trend_min_span_days = 0.01
    out = build_trend_summary(
        settings=settings,
        db=sqlite_session,
        asset_zone_id=zone,
        metric_name="m_trunc",
        org_id=None,
        effective_from=None,
        effective_to=None,
    )
    assert out.truncated is True
    assert len(out.points) == 2
    assert [p.value for p in out.points] == [5.0, 10.0]
    assert out.min_value == 0.0
    assert out.max_value == 10.0
    assert abs(out.mean_value - 5.0) < 1e-9
    assert out.latest_value == 10.0
    assert out.delta_first_to_latest == 10.0
    assert out.simple_slope_per_day is not None

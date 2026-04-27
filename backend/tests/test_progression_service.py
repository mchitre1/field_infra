from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import Settings
from app.models.detection import Detection, DetectionType
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.models.progression_metric import ProgressionMetric
from app.services import alignment
from app.services.progression import run_progression_for_inspection


def _inspection(**kwargs):
    defaults = dict(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint="site-a",
        asset_hint="tower-1",
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=1,
        status=InspectionStatus.detections_ready,
        latitude=40.0,
        longitude=-75.0,
    )
    defaults.update(kwargs)
    return Inspection(**defaults)


def test_progression_after_alignment_persists_crack_metrics(sqlite_session):
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    baseline = _inspection(capture_timestamp=t0)
    target = _inspection(capture_timestamp=t0 + timedelta(days=1))
    sqlite_session.add_all([baseline, target])
    sqlite_session.commit()
    f1, f2 = uuid4(), uuid4()
    d1 = Detection(
        id=uuid4(),
        inspection_id=baseline.id,
        frame_id=f1,
        detection_type=DetectionType.defect,
        class_name="crack",
        confidence=0.9,
        centroid_x=0.3,
        centroid_y=0.3,
        asset_zone_hint="site-a:crack",
        bbox_xmin=0.1,
        bbox_ymin=0.1,
        bbox_xmax=0.5,
        bbox_ymax=0.5,
        model_name="yolo",
        model_version="v1",
    )
    d2 = Detection(
        id=uuid4(),
        inspection_id=target.id,
        frame_id=f2,
        detection_type=DetectionType.defect,
        class_name="crack",
        confidence=0.85,
        centroid_x=0.31,
        centroid_y=0.29,
        asset_zone_hint="site-a:crack",
        bbox_xmin=0.12,
        bbox_ymin=0.1,
        bbox_xmax=0.62,
        bbox_ymax=0.5,
        model_name="yolo",
        model_version="v1",
    )
    sqlite_session.add_all([d1, d2])
    sqlite_session.commit()

    settings = Settings(database_url="sqlite://", s3_bucket="b", aws_region="us-east-1")
    alignment.run_alignment_for_inspection(
        settings=settings, db=sqlite_session, inspection_id=target.id
    )
    n = run_progression_for_inspection(
        settings=settings, db=sqlite_session, inspection_id=target.id
    )
    assert n >= 2
    rows = sqlite_session.scalars(
        select(ProgressionMetric).where(ProgressionMetric.target_inspection_id == target.id)
    ).all()
    names = {r.metric_name for r in rows}
    assert "crack_size_delta" in names
    assert "crack_growth_rate" in names
    sqlite_session.refresh(target)
    assert target.progression_metric_count == n


def test_progression_does_not_delete_metrics_when_not_alignment_ready(sqlite_session):
    baseline = _inspection(capture_timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc))
    target = _inspection(
        capture_timestamp=datetime(2026, 3, 2, tzinfo=timezone.utc),
        status=InspectionStatus.alignment_failed,
    )
    sqlite_session.add_all([baseline, target])
    sqlite_session.commit()
    sqlite_session.add(
        ProgressionMetric(
            id=uuid4(),
            asset_zone_id="zone-x",
            baseline_inspection_id=baseline.id,
            target_inspection_id=target.id,
            alignment_pair_id=None,
            metric_name="crack_growth_rate",
            metric_unit="normalized_units_per_day",
            value=0.01,
            payload=None,
        )
    )
    sqlite_session.commit()

    settings = Settings(database_url="sqlite://", s3_bucket="b", aws_region="us-east-1")
    n = run_progression_for_inspection(
        settings=settings, db=sqlite_session, inspection_id=target.id
    )
    assert n == 0
    count = sqlite_session.scalar(
        select(func.count()).select_from(ProgressionMetric).where(
            ProgressionMetric.target_inspection_id == target.id
        )
    )
    assert count == 1


def test_progression_clears_when_no_baseline(sqlite_session):
    target = _inspection(capture_timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))
    sqlite_session.add(target)
    sqlite_session.commit()
    settings = Settings(database_url="sqlite://", s3_bucket="b", aws_region="us-east-1")
    alignment.run_alignment_for_inspection(
        settings=settings, db=sqlite_session, inspection_id=target.id
    )
    run_progression_for_inspection(settings=settings, db=sqlite_session, inspection_id=target.id)
    sqlite_session.refresh(target)
    assert target.progression_metric_count == 0

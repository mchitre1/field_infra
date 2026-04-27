import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.change_event import ChangeEvent
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.models.progression_metric import ProgressionMetric
from app.services.anomaly_timeline import build_timeline


def test_timeline_sorted_mixed_sources(sqlite_session: Session):
    org = uuid.uuid4()
    zone = "zone-tl-1"
    i_early = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    i_late = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    sqlite_session.add_all(
        [
            Inspection(
                id=i_late,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="site-x",
                asset_hint="a",
                capture_timestamp=t1,
                s3_bucket="b",
                s3_key="k2",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
            Inspection(
                id=i_early,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="site-x",
                asset_hint="a",
                capture_timestamp=t0,
                s3_bucket="b",
                s3_key="k1",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
        ]
    )
    sqlite_session.commit()

    ce = ChangeEvent(
        id=uuid.uuid4(),
        asset_zone_id=zone,
        inspection_id=i_late,
        event_type="appeared",
        event_payload={"class_name": "crack"},
    )
    pm = ProgressionMetric(
        id=uuid.uuid4(),
        asset_zone_id=zone,
        baseline_inspection_id=i_early,
        target_inspection_id=i_early,
        metric_name="crack_growth_rate",
        metric_unit="u",
        value=0.5,
        payload=None,
    )
    sqlite_session.add_all([ce, pm])
    sqlite_session.commit()

    settings = Settings()
    entries = build_timeline(
        settings=settings,
        db=sqlite_session,
        asset_zone_id=zone,
        org_id=org,
        site_hint="site-x",
        effective_from=None,
        effective_to=None,
        event_type=None,
        metric_name=None,
    )
    kinds = [e.entry_kind for e in entries]
    assert kinds == ["progression_metric", "change_event"]

    def _utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    assert _utc(entries[0].effective_at) == t0
    assert _utc(entries[1].effective_at) == t1
    assert entries[1].refs.get("event_type") == "appeared"


def test_timeline_metric_name_filter(sqlite_session: Session):
    org = uuid.uuid4()
    zone = "zone-tl-2"
    ins_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    sqlite_session.add(
        Inspection(
            id=ins_id,
            org_id=org,
            source_type=SourceType.drone,
            site_hint=None,
            asset_hint=None,
            capture_timestamp=None,
            s3_bucket="b",
            s3_key="k",
            content_type="image/jpeg",
            byte_size=10,
            status=InspectionStatus.alignment_ready,
        )
    )
    sqlite_session.commit()
    sqlite_session.add_all(
        [
            ProgressionMetric(
                id=uuid.uuid4(),
                asset_zone_id=zone,
                baseline_inspection_id=ins_id,
                target_inspection_id=ins_id,
                metric_name="keep_me",
                metric_unit="u",
                value=1.0,
                payload=None,
            ),
            ProgressionMetric(
                id=uuid.uuid4(),
                asset_zone_id=zone,
                baseline_inspection_id=ins_id,
                target_inspection_id=ins_id,
                metric_name="other",
                metric_unit="u",
                value=2.0,
                payload=None,
            ),
        ]
    )
    sqlite_session.commit()

    settings = Settings()
    entries = build_timeline(
        settings=settings,
        db=sqlite_session,
        asset_zone_id=zone,
        org_id=None,
        site_hint=None,
        effective_from=None,
        effective_to=None,
        event_type=None,
        metric_name="keep_me",
    )
    assert len(entries) == 1
    assert "keep_me" in entries[0].summary

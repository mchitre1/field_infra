import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.alignment import Alignment
from app.models.change_event import ChangeEvent
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.models.maintenance_recommendation import MaintenanceRecommendation
from app.models.progression_metric import ProgressionMetric
from app.models.risk_rule import RiskRule
from app.services.recommendation_engine import run_recommendations_for_inspection
from app.services.recommendation_rules import sla_days_for_label


def test_engine_writes_ranked_rows_and_sla(sqlite_session: Session):
    org = uuid.uuid4()
    base_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tgt_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    cap = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    sqlite_session.add_all(
        [
            Inspection(
                id=base_id,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="s",
                asset_hint="tower-1",
                capture_timestamp=cap - timedelta(days=30),
                s3_bucket="b",
                s3_key="k0",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
            Inspection(
                id=tgt_id,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="s",
                asset_hint="tower-1",
                capture_timestamp=cap,
                s3_bucket="b",
                s3_key="k1",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
        ]
    )
    sqlite_session.commit()

    fid = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    sqlite_session.add(
        Frame(
            id=fid,
            inspection_id=tgt_id,
            frame_index=0,
            frame_timestamp_ms=0,
            s3_bucket="b",
            s3_key="f.jpg",
            source_type=SourceType.drone,
        )
    )
    sqlite_session.commit()

    zone_hot = "hot-zone"
    zone_calm = "calm-zone"
    det_hot = Detection(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        inspection_id=tgt_id,
        frame_id=fid,
        detection_type=DetectionType.defect,
        class_name="crack",
        confidence=0.95,
        bbox_xmin=0.1,
        bbox_ymin=0.1,
        bbox_xmax=0.2,
        bbox_ymax=0.2,
        geometry=None,
        model_name="yolo",
        model_version="v1",
        asset_zone_hint=zone_hot,
    )
    det_calm = Detection(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        inspection_id=tgt_id,
        frame_id=fid,
        detection_type=DetectionType.defect,
        class_name="crack",
        confidence=0.52,
        bbox_xmin=0.5,
        bbox_ymin=0.5,
        bbox_xmax=0.6,
        bbox_ymax=0.6,
        geometry=None,
        model_name="yolo",
        model_version="v1",
        asset_zone_hint=zone_calm,
    )
    sqlite_session.add_all([det_hot, det_calm])
    sqlite_session.commit()

    sqlite_session.add(
        ChangeEvent(
            id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            asset_zone_id=zone_calm,
            inspection_id=tgt_id,
            event_type="appeared",
            event_payload={"class_name": "crack"},
        )
    )
    sqlite_session.add(
        ProgressionMetric(
            id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            asset_zone_id=zone_hot,
            baseline_inspection_id=base_id,
            target_inspection_id=tgt_id,
            metric_name="crack_growth_rate",
            metric_unit="u",
            value=0.01,
            payload=None,
        )
    )
    sqlite_session.add(
        Alignment(
            id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            asset_zone_id=zone_hot,
            baseline_inspection_id=base_id,
            target_inspection_id=tgt_id,
            baseline_detection_id=det_hot.id,
            target_detection_id=det_hot.id,
            alignment_score=0.8,
            change_type="persisted",
        )
    )
    sqlite_session.commit()

    n = run_recommendations_for_inspection(settings=Settings(), db=sqlite_session, inspection_id=tgt_id)
    assert n >= 2
    rows = sqlite_session.scalars(
        select(MaintenanceRecommendation)
        .where(MaintenanceRecommendation.target_inspection_id == tgt_id)
        .order_by(MaintenanceRecommendation.priority_rank.asc())
    ).all()
    assert rows[0].priority_rank == 1
    assert {r.asset_zone_id for r in rows} == {zone_hot, zone_calm}
    scores = [r.priority_score for r in rows]
    assert scores == sorted(scores, reverse=True)
    insp = sqlite_session.get(Inspection, tgt_id)
    assert insp is not None
    assert insp.recommendation_count == n
    settings = Settings()
    d0 = sla_days_for_label(settings=settings, label=rows[0].priority_label)
    expected0 = cap + timedelta(seconds=d0 * 86400)
    sla0 = rows[0].sla_target_at
    if sla0.tzinfo is None:
        sla0 = sla0.replace(tzinfo=timezone.utc)
    assert abs((sla0 - expected0).total_seconds()) < 2


def test_engine_includes_asset_zone_from_progression_only(sqlite_session: Session):
    """Zones that appear only on progression_metrics must still get a recommendation row."""
    org = uuid.uuid4()
    base_id = uuid.uuid4()
    tgt_id = uuid.uuid4()
    cap = datetime(2025, 7, 1, tzinfo=timezone.utc)
    sqlite_session.add_all(
        [
            Inspection(
                id=base_id,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="s",
                asset_hint="t",
                capture_timestamp=cap - timedelta(days=1),
                s3_bucket="b",
                s3_key="k0",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
            Inspection(
                id=tgt_id,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="s",
                asset_hint="t",
                capture_timestamp=cap,
                s3_bucket="b",
                s3_key="k1",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
        ]
    )
    sqlite_session.commit()
    zone_pm_only = "progression-only-zone"
    sqlite_session.add(
        ProgressionMetric(
            id=uuid.uuid4(),
            asset_zone_id=zone_pm_only,
            baseline_inspection_id=base_id,
            target_inspection_id=tgt_id,
            metric_name="crack_growth_rate",
            metric_unit="u",
            value=0.01,
            payload=None,
        )
    )
    sqlite_session.commit()

    n = run_recommendations_for_inspection(settings=Settings(), db=sqlite_session, inspection_id=tgt_id)
    assert n == 1
    rows = sqlite_session.scalars(
        select(MaintenanceRecommendation).where(
            MaintenanceRecommendation.target_inspection_id == tgt_id
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].asset_zone_id == zone_pm_only
    insp = sqlite_session.get(Inspection, tgt_id)
    assert insp is not None
    assert insp.recommendation_count == 1


def test_recommendation_engine_persists_sla_days_multiplier(sqlite_session: Session):
    org = uuid.uuid4()
    tgt_id = uuid.uuid4()
    cap = datetime(2025, 8, 15, tzinfo=timezone.utc)
    sqlite_session.add(
        Inspection(
            id=tgt_id,
            org_id=org,
            source_type=SourceType.drone,
            site_hint="s",
            asset_hint="t",
            capture_timestamp=cap,
            s3_bucket="b",
            s3_key="k1",
            content_type="image/jpeg",
            byte_size=10,
            status=InspectionStatus.alignment_ready,
        )
    )
    sqlite_session.commit()
    fid = uuid.uuid4()
    zone_id = "sla-mul-zone"
    sqlite_session.add(
        Frame(
            id=fid,
            inspection_id=tgt_id,
            frame_index=0,
            frame_timestamp_ms=0,
            s3_bucket="b",
            s3_key="f.jpg",
            source_type=SourceType.drone,
        )
    )
    sqlite_session.commit()
    sqlite_session.add(
        Detection(
            id=uuid.uuid4(),
            inspection_id=tgt_id,
            frame_id=fid,
            detection_type=DetectionType.defect,
            class_name="crack",
            confidence=0.95,
            bbox_xmin=0.1,
            bbox_ymin=0.1,
            bbox_xmax=0.2,
            bbox_ymax=0.2,
            geometry=None,
            model_name="yolo",
            model_version="v1",
            asset_zone_hint=zone_id,
        )
    )
    sqlite_session.add(
        RiskRule(
            id=uuid.uuid4(),
            org_id=None,
            priority=1,
            enabled=True,
            name="halve sla",
            match={"match_version": 1},
            effect={"sla_days_multiplier": 0.5, "score_add": 0.0, "score_multiplier": 1.0},
        )
    )
    sqlite_session.commit()

    settings = Settings()
    n = run_recommendations_for_inspection(
        settings=settings, db=sqlite_session, inspection_id=tgt_id
    )
    assert n == 1
    row = sqlite_session.scalars(
        select(MaintenanceRecommendation).where(
            MaintenanceRecommendation.target_inspection_id == tgt_id
        )
    ).first()
    assert row is not None
    base_days = sla_days_for_label(settings=settings, label=row.priority_label)
    assert math.isclose(row.sla_days_suggested, base_days * 0.5, rel_tol=0, abs_tol=1e-6)

import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.change_event import ChangeEvent
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.models.progression_metric import ProgressionMetric
from app.models.risk_rule import RiskRule
from app.services.recommendation_rules import priority_label_for_score, score_zone, sla_days_for_label


def _det(conf: float, cls: str = "crack", frame_id: uuid.UUID | None = None) -> Detection:
    return Detection(
        id=uuid.uuid4(),
        inspection_id=uuid.uuid4(),
        frame_id=frame_id or uuid.uuid4(),
        detection_type=DetectionType.defect,
        class_name=cls,
        confidence=conf,
        bbox_xmin=0.1,
        bbox_ymin=0.1,
        bbox_xmax=0.2,
        bbox_ymax=0.2,
        geometry=None,
        model_name="yolo",
        model_version="v1",
        asset_zone_hint="zone-a",
    )


def test_score_increases_with_higher_confidence():
    s = Settings()
    low, _, _, _ = score_zone(settings=s, zone_id="z", detections=[_det(0.51)], change_events=[], progression_metrics=[])
    high, _, _, _ = score_zone(settings=s, zone_id="z", detections=[_det(0.95)], change_events=[], progression_metrics=[])
    assert high > low


def test_appeared_event_adds_score():
    s = Settings()
    ev = ChangeEvent(
        id=uuid.uuid4(),
        asset_zone_id="z",
        inspection_id=uuid.uuid4(),
        event_type="appeared",
        event_payload={"class_name": "crack"},
    )
    base, _, _, _ = score_zone(settings=s, zone_id="z", detections=[], change_events=[], progression_metrics=[])
    with_ev, _, _, _ = score_zone(settings=s, zone_id="z", detections=[], change_events=[ev], progression_metrics=[])
    assert with_ev > base


def test_crack_growth_above_floor_adds():
    s = Settings()
    pm = ProgressionMetric(
        id=uuid.uuid4(),
        asset_zone_id="z",
        baseline_inspection_id=uuid.uuid4(),
        target_inspection_id=uuid.uuid4(),
        metric_name="crack_growth_rate",
        metric_unit="u",
        value=0.01,
        payload=None,
    )
    without, _, _, _ = score_zone(settings=s, zone_id="z", detections=[], change_events=[], progression_metrics=[])
    with_pm, factors, _, _ = score_zone(
        settings=s, zone_id="z", detections=[], change_events=[], progression_metrics=[pm]
    )
    assert with_pm > without
    assert any(f.get("kind") == "progression_metric" for f in factors)


def test_priority_label_bands():
    s = Settings()
    assert priority_label_for_score(settings=s, score=100.0) == "critical"
    assert priority_label_for_score(settings=s, score=50.0) == "high"
    assert priority_label_for_score(settings=s, score=20.0) == "medium"
    assert priority_label_for_score(settings=s, score=0.0) == "low"


def test_sla_days_mapping():
    s = Settings()
    assert sla_days_for_label(settings=s, label="critical") == s.recommend_sla_days_critical


def test_score_zone_applies_persisted_risk_rule(sqlite_session: Session):
    fid = uuid.uuid4()
    iid = uuid.uuid4()
    insp = Inspection(
        id=iid,
        org_id=None,
        source_type=SourceType.fixed_camera,
        site_hint="coast",
        asset_hint="tower-A",
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.alignment_ready,
        latitude=30.0,
        longitude=-80.0,
        extra_metadata={"weather_code": 2},
    )
    sqlite_session.add(insp)
    sqlite_session.commit()
    sqlite_session.add(
        Frame(
            id=fid,
            inspection_id=iid,
            frame_index=0,
            frame_timestamp_ms=0,
            s3_bucket="b",
            s3_key="f.jpg",
            source_type=SourceType.fixed_camera,
            latitude=30.1,
            longitude=-80.1,
        )
    )
    sqlite_session.commit()
    d = _det(0.9, frame_id=fid)
    d.inspection_id = iid
    sqlite_session.add(d)
    sqlite_session.add(
        RiskRule(
            id=uuid.uuid4(),
            org_id=None,
            priority=10,
            enabled=True,
            name="fixed coastal boost",
            match={
                "match_version": 1,
                "source_types": ["fixed_camera"],
                "lat_min": 25.0,
                "lat_max": 35.0,
                "lon_min": -85.0,
                "lon_max": -75.0,
                "inspection_metadata_contains": {"weather_code": 2},
            },
            effect={"score_add": 100.0, "score_multiplier": 1.0, "sla_days_multiplier": 0.5},
        )
    )
    sqlite_session.commit()
    fr = sqlite_session.get(Frame, fid)
    assert fr is not None
    frames = {fid: fr}
    base, _, _, _ = score_zone(
        settings=Settings(),
        zone_id="zone-a",
        detections=[d],
        change_events=[],
        progression_metrics=[],
    )
    boosted, factors, _, sla_mul = score_zone(
        settings=Settings(),
        zone_id="zone-a",
        detections=[d],
        change_events=[],
        progression_metrics=[],
        db=sqlite_session,
        inspection=insp,
        frames_by_id=frames,  # type: ignore[arg-type]
    )
    assert boosted > base
    assert any(f.get("kind") == "risk_rule" for f in factors)
    assert sla_mul == 0.5

import uuid

from app.core.config import Settings
from app.models.change_event import ChangeEvent
from app.models.detection import Detection, DetectionType
from app.models.progression_metric import ProgressionMetric
from app.services.recommendation_rules import priority_label_for_score, score_zone, sla_days_for_label


def _det(conf: float, cls: str = "crack") -> Detection:
    return Detection(
        id=uuid.uuid4(),
        inspection_id=uuid.uuid4(),
        frame_id=uuid.uuid4(),
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
    low, _, _ = score_zone(settings=s, zone_id="z", detections=[_det(0.51)], change_events=[], progression_metrics=[])
    high, _, _ = score_zone(settings=s, zone_id="z", detections=[_det(0.95)], change_events=[], progression_metrics=[])
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
    base, _, _ = score_zone(settings=s, zone_id="z", detections=[], change_events=[], progression_metrics=[])
    with_ev, _, _ = score_zone(settings=s, zone_id="z", detections=[], change_events=[ev], progression_metrics=[])
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
    without, _, _ = score_zone(settings=s, zone_id="z", detections=[], change_events=[], progression_metrics=[])
    with_pm, factors, _ = score_zone(settings=s, zone_id="z", detections=[], change_events=[], progression_metrics=[pm])
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

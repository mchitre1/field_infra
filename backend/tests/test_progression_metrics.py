from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.detection import Detection, DetectionType
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.services.progression_crack import build_crack_metric_drafts, crack_size_proxy
from app.services.progression_vegetation import build_vegetation_metric_drafts, vegetation_area


def _ins(capture: datetime | None):
    return Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint="s",
        asset_hint="a",
        capture_timestamp=capture,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=1,
        status=InspectionStatus.alignment_ready,
        latitude=None,
        longitude=None,
    )


def _det(*, bbox, cls="crack", dtype=DetectionType.defect):
    xmin, ymin, xmax, ymax = bbox
    return Detection(
        id=uuid4(),
        inspection_id=uuid4(),
        frame_id=uuid4(),
        detection_type=dtype,
        class_name=cls,
        confidence=0.9,
        bbox_xmin=xmin,
        bbox_ymin=ymin,
        bbox_xmax=xmax,
        bbox_ymax=ymax,
        model_name="y",
        model_version="v1",
    )


def test_crack_size_proxy_bbox_width():
    d = _det(bbox=(0.1, 0.2, 0.5, 0.3))
    assert crack_size_proxy(d, "bbox_width") == 0.4


def test_crack_growth_rate_with_sufficient_delta_t():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=2)
    bi = _ins(t0)
    ti = _ins(t1)
    b = _det(bbox=(0.0, 0.0, 0.2, 0.1))
    t = _det(bbox=(0.0, 0.0, 0.4, 0.1))
    drafts = build_crack_metric_drafts(
        baseline=b,
        target=t,
        baseline_inspection=bi,
        target_inspection=ti,
        crack_metric="bbox_width",
        min_time_delta_seconds=3600.0,
    )
    names = {d.metric_name for d in drafts}
    assert "crack_size_delta" in names
    assert "crack_growth_rate" in names
    rate = next(d for d in drafts if d.metric_name == "crack_growth_rate")
    assert rate.value == 0.1


def test_crack_skips_rate_when_delta_t_below_min():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=30)
    bi = _ins(t0)
    ti = _ins(t1)
    b = _det(bbox=(0.0, 0.0, 0.2, 0.1))
    t = _det(bbox=(0.0, 0.0, 0.4, 0.1))
    drafts = build_crack_metric_drafts(
        baseline=b,
        target=t,
        baseline_inspection=bi,
        target_inspection=ti,
        crack_metric="bbox_width",
        min_time_delta_seconds=3600.0,
    )
    assert [d.metric_name for d in drafts] == ["crack_size_delta"]


def test_vegetation_delta_and_rate():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=1)
    bi = _ins(t0)
    ti = _ins(t1)
    b = _det(bbox=(0.0, 0.0, 0.1, 0.1), cls="vegetation_encroachment", dtype=DetectionType.environmental_hazard)
    tgt = _det(bbox=(0.0, 0.0, 0.2, 0.1), cls="vegetation_encroachment", dtype=DetectionType.environmental_hazard)
    assert abs(vegetation_area(b, "bbox_area") - 0.01) < 1e-12
    assert abs(vegetation_area(tgt, "bbox_area") - 0.02) < 1e-12
    drafts = build_vegetation_metric_drafts(
        baseline=b,
        target=tgt,
        baseline_inspection=bi,
        target_inspection=ti,
        vegetation_metric="bbox_area",
        min_time_delta_seconds=3600.0,
    )
    assert {d.metric_name for d in drafts} == {
        "vegetation_encroachment_delta",
        "vegetation_encroachment_rate",
    }
    delta = next(d for d in drafts if d.metric_name == "vegetation_encroachment_delta")
    assert abs(delta.value - 0.01) < 1e-9

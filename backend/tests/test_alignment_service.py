from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.config import Settings
from app.models.detection import Detection, DetectionType
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.services import alignment


def _inspection(*, status: InspectionStatus, capture=None):
    return Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint="site-a",
        asset_hint="tower-1",
        capture_timestamp=capture,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=1,
        status=status,
        latitude=40.0,
        longitude=-75.0,
    )


def test_run_alignment_for_inspection_persists_pairs_and_events(sqlite_session):
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    baseline = _inspection(
        status=InspectionStatus.detections_ready, capture=t0
    )
    target = _inspection(
        status=InspectionStatus.detections_ready,
        capture=t0 + timedelta(hours=2),
    )
    sqlite_session.add_all([baseline, target])
    sqlite_session.commit()
    d1 = Detection(
        id=uuid4(),
        inspection_id=baseline.id,
        frame_id=uuid4(),
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
        frame_id=uuid4(),
        detection_type=DetectionType.defect,
        class_name="crack",
        confidence=0.85,
        centroid_x=0.31,
        centroid_y=0.29,
        asset_zone_hint="site-a:crack",
        bbox_xmin=0.12,
        bbox_ymin=0.1,
        bbox_xmax=0.52,
        bbox_ymax=0.5,
        model_name="yolo",
        model_version="v1",
    )
    sqlite_session.add_all([d1, d2])
    sqlite_session.commit()

    settings = Settings(database_url="sqlite://", s3_bucket="b", aws_region="us-east-1")
    pair_count, event_count = alignment.run_alignment_for_inspection(
        settings=settings, db=sqlite_session, inspection_id=target.id
    )
    assert pair_count >= 1
    assert event_count == 0
    sqlite_session.refresh(target)
    assert target.status == InspectionStatus.alignment_ready
    assert target.aligned_pair_count == pair_count


def test_run_alignment_marks_failed_on_error(sqlite_session, monkeypatch):
    t0 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    baseline = _inspection(
        status=InspectionStatus.detections_ready, capture=t0
    )
    target = _inspection(
        status=InspectionStatus.detections_ready,
        capture=t0 + timedelta(hours=1),
    )
    sqlite_session.add_all([baseline, target])
    sqlite_session.commit()
    sqlite_session.add_all(
        [
            Detection(
                id=uuid4(),
                inspection_id=baseline.id,
                frame_id=uuid4(),
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
            ),
            Detection(
                id=uuid4(),
                inspection_id=target.id,
                frame_id=uuid4(),
                detection_type=DetectionType.defect,
                class_name="crack",
                confidence=0.85,
                centroid_x=0.31,
                centroid_y=0.29,
                asset_zone_hint="site-a:crack",
                bbox_xmin=0.12,
                bbox_ymin=0.1,
                bbox_xmax=0.52,
                bbox_ymax=0.5,
                model_name="yolo",
                model_version="v1",
            ),
        ]
    )
    sqlite_session.commit()

    settings = Settings(database_url="sqlite://", s3_bucket="b", aws_region="us-east-1")
    monkeypatch.setattr(alignment, "match_detection_sets", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        alignment.run_alignment_for_inspection(
            settings=settings, db=sqlite_session, inspection_id=target.id
        )
    except RuntimeError:
        pass
    sqlite_session.refresh(target)
    assert target.status == InspectionStatus.alignment_failed
    assert target.extra_metadata is not None
    assert target.extra_metadata.get("alignment_error") == "boom"

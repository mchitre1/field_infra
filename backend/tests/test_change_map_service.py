import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.alignment import Alignment
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.services.change_map import build_change_map


def _seed_pair(sqlite_session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    org = uuid.uuid4()
    base_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tgt_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    f_base = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    f_tgt = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    d_b = uuid.UUID("11111111-1111-1111-1111-111111111111")
    d_t = uuid.UUID("22222222-2222-2222-2222-222222222222")

    sqlite_session.add_all(
        [
            Inspection(
                id=base_id,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="s1",
                asset_hint="a1",
                capture_timestamp=None,
                s3_bucket="b",
                s3_key="k1",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
            Inspection(
                id=tgt_id,
                org_id=org,
                source_type=SourceType.drone,
                site_hint="s1",
                asset_hint="a1",
                capture_timestamp=None,
                s3_bucket="b",
                s3_key="k2",
                content_type="image/jpeg",
                byte_size=10,
                status=InspectionStatus.alignment_ready,
            ),
        ]
    )
    sqlite_session.commit()
    sqlite_session.add_all(
        [
            Frame(
                id=f_base,
                inspection_id=base_id,
                frame_index=0,
                frame_timestamp_ms=0,
                s3_bucket="fb",
                s3_key="f0.jpg",
                width=1920,
                height=1080,
                source_type=SourceType.drone,
            ),
            Frame(
                id=f_tgt,
                inspection_id=tgt_id,
                frame_index=0,
                frame_timestamp_ms=0,
                s3_bucket="fb",
                s3_key="f1.jpg",
                width=1920,
                height=1080,
                source_type=SourceType.drone,
            ),
        ]
    )
    sqlite_session.commit()
    sqlite_session.add_all(
        [
            Detection(
                id=d_b,
                inspection_id=base_id,
                frame_id=f_base,
                detection_type=DetectionType.defect,
                class_name="crack",
                confidence=0.9,
                bbox_xmin=0.1,
                bbox_ymin=0.2,
                bbox_xmax=0.3,
                bbox_ymax=0.4,
                geometry=None,
                model_name="yolo",
                model_version="v1",
            ),
            Detection(
                id=d_t,
                inspection_id=tgt_id,
                frame_id=f_tgt,
                detection_type=DetectionType.defect,
                class_name="crack",
                confidence=0.88,
                bbox_xmin=0.12,
                bbox_ymin=0.22,
                bbox_xmax=0.32,
                bbox_ymax=0.42,
                geometry=None,
                model_name="yolo",
                model_version="v1",
            ),
        ]
    )
    sqlite_session.commit()
    aid = uuid.UUID("33333333-3333-3333-3333-333333333333")
    sqlite_session.add(
        Alignment(
            id=aid,
            asset_zone_id="zone-1",
            baseline_inspection_id=base_id,
            target_inspection_id=tgt_id,
            baseline_detection_id=d_b,
            target_detection_id=d_t,
            alignment_score=0.71,
            change_type="persisted",
        )
    )
    sqlite_session.commit()
    return base_id, tgt_id


def test_change_map_two_features_for_persisted(sqlite_session: Session):
    base_id, tgt_id = _seed_pair(sqlite_session)
    settings = Settings()
    s3 = MagicMock()
    s3.generate_presigned_url = MagicMock(return_value="https://example.com/get")
    out = build_change_map(
        settings=settings,
        db=sqlite_session,
        s3_client=s3,
        baseline_inspection_id=base_id,
        target_inspection_id=tgt_id,
        asset_zone_id=None,
        frame_id=None,
        include_frame_urls=True,
    )
    assert out.truncated is False
    assert len(out.features) == 2
    sides = {f.side for f in out.features}
    assert sides == {"baseline", "target"}
    assert all(f.change_type == "persisted" for f in out.features)
    assert all(f.alignment_score == 0.71 for f in out.features)
    assert {f.geometry.xmin for f in out.features} == {0.1, 0.12}
    s3.generate_presigned_url.assert_called()


def test_change_map_frame_filter(sqlite_session: Session):
    base_id, tgt_id = _seed_pair(sqlite_session)
    settings = Settings()
    s3 = MagicMock()
    tgt_frame = sqlite_session.scalars(select(Frame).where(Frame.inspection_id == tgt_id)).first()
    assert tgt_frame is not None
    out = build_change_map(
        settings=settings,
        db=sqlite_session,
        s3_client=s3,
        baseline_inspection_id=base_id,
        target_inspection_id=tgt_id,
        asset_zone_id=None,
        frame_id=tgt_frame.id,
        include_frame_urls=False,
    )
    assert len(out.features) == 1
    assert out.features[0].side == "target"


def test_change_map_missing_inspection_raises(sqlite_session: Session):
    base_id, tgt_id = _seed_pair(sqlite_session)
    settings = Settings()
    s3 = MagicMock()
    with pytest.raises(LookupError):
        build_change_map(
            settings=settings,
            db=sqlite_session,
            s3_client=s3,
            baseline_inspection_id=uuid.uuid4(),
            target_inspection_id=tgt_id,
            asset_zone_id=None,
            frame_id=None,
            include_frame_urls=False,
        )

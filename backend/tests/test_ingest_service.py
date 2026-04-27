from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.core.config import Settings
from app.jobs.publisher import publish_ingest_job
from app.models.detection import Detection
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.services import detection_pipeline
from app.services import frame_extraction
from app.services import ingest as ingest_service


@pytest.fixture
def inspection_row() -> Inspection:
    return Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=12,
        status=InspectionStatus.stored,
        latitude=None,
        longitude=None,
    )


def test_publish_sets_queued(inspection_row):
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="b",
        sqs_queue_url="https://sqs.example.com/q",
        aws_region="us-east-1",
    )
    db = MagicMock()
    sqs = MagicMock()
    ok = publish_ingest_job(
        settings=settings, db=db, inspection=inspection_row, sqs_client=sqs
    )
    assert ok is True
    sqs.send_message.assert_called_once()
    assert inspection_row.status == InspectionStatus.queued
    db.add.assert_called()
    assert db.commit.call_count >= 1


def test_publish_no_queue_skips_sqs(inspection_row):
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="b",
        sqs_queue_url="",
        aws_region="us-east-1",
    )
    db = MagicMock()
    sqs = MagicMock()
    ok = publish_ingest_job(
        settings=settings, db=db, inspection=inspection_row, sqs_client=sqs
    )
    assert ok is True
    sqs.send_message.assert_not_called()


def test_publish_failure_non_client_error_sets_pending_queue(inspection_row):
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="b",
        sqs_queue_url="https://sqs.example.com/q",
        aws_region="us-east-1",
    )
    db = MagicMock()
    sqs = MagicMock()
    sqs.send_message.side_effect = RuntimeError("unexpected")
    ok = publish_ingest_job(
        settings=settings, db=db, inspection=inspection_row, sqs_client=sqs
    )
    assert ok is False
    assert inspection_row.status == InspectionStatus.stored_pending_queue
    assert inspection_row.last_queue_error is not None


def test_publish_failure_sets_pending_queue(inspection_row):
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="b",
        sqs_queue_url="https://sqs.example.com/q",
        aws_region="us-east-1",
    )
    db = MagicMock()
    sqs = MagicMock()
    sqs.send_message.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "SendMessage"
    )
    ok = publish_ingest_job(
        settings=settings, db=db, inspection=inspection_row, sqs_client=sqs
    )
    assert ok is False
    assert inspection_row.status == InspectionStatus.stored_pending_queue
    assert inspection_row.last_queue_error is not None


@pytest.mark.asyncio
async def test_multipart_deletes_s3_when_db_commit_fails():
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="bucket",
        sqs_queue_url="",
        aws_region="us-east-1",
    )
    db = MagicMock()
    db.commit.side_effect = RuntimeError("db unavailable")
    db.add = MagicMock()
    s3 = MagicMock()
    sqs = MagicMock()

    upload = MagicMock()
    upload.content_type = "image/jpeg"
    upload.filename = "pic.jpg"
    upload.read = AsyncMock(side_effect=[b"hello", b""])

    with pytest.raises(HTTPException) as exc:
        await ingest_service.ingest_multipart_upload(
            settings=settings,
            db=db,
            s3_client=s3,
            sqs_client=sqs,
            file=upload,
            source_type=SourceType.drone,
            org_id=None,
            site_hint=None,
            asset_hint=None,
            capture_timestamp=None,
            latitude=None,
            longitude=None,
        )
    assert exc.value.status_code == 500
    s3.delete_object.assert_called_once()


def test_extract_and_store_frames_image(sqlite_session):
    inspection = Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.mobile,
        site_hint="line-1",
        asset_hint="tower-2",
        capture_timestamp=None,
        s3_bucket="raw-b",
        s3_key="raw/a.jpg",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.queued,
        latitude=1.0,
        longitude=2.0,
    )
    sqlite_session.add(inspection)
    sqlite_session.commit()
    s3 = MagicMock()
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=buf.getvalue()))
    }
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="raw-b",
        frames_bucket="frames-b",
        aws_region="us-east-1",
        sqs_queue_url="",
    )
    count = frame_extraction.extract_and_store_frames(
        settings=settings,
        db=sqlite_session,
        s3_client=s3,
        inspection_id=inspection.id,
        extraction_hints={"fps": 1.0, "max_frames": 10},
    )
    assert count == 1
    got = sqlite_session.query(Frame).filter(Frame.inspection_id == inspection.id).all()
    assert len(got) == 1
    sqlite_session.refresh(inspection)
    assert inspection.status == InspectionStatus.frames_extracted
    assert inspection.frame_count == 1
    s3.put_object.assert_called_once()


def test_extract_and_store_frames_video_uses_hints(sqlite_session, monkeypatch):
    inspection = Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="raw-b",
        s3_key="raw/a.mp4",
        content_type="video/mp4",
        byte_size=10,
        status=InspectionStatus.queued,
        latitude=None,
        longitude=None,
    )
    sqlite_session.add(inspection)
    sqlite_session.commit()
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"video"))}

    def fake_extract(raw, *, fps, max_frames):
        assert fps == 2.5
        assert max_frames == 5
        return (
            [
                frame_extraction.ExtractedFrame(
                    frame_index=0,
                    frame_timestamp_ms=0,
                    image_jpeg=b"jpeg",
                    width=4,
                    height=3,
                )
            ],
            {"video_duration_ms": 1000, "video_fps": 30.0, "video_codec": "h264"},
        )

    monkeypatch.setattr(frame_extraction, "_extract_video_frames", fake_extract)
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="raw-b",
        frames_bucket="frames-b",
        aws_region="us-east-1",
        sqs_queue_url="",
    )
    count = frame_extraction.extract_and_store_frames(
        settings=settings,
        db=sqlite_session,
        s3_client=s3,
        inspection_id=inspection.id,
        extraction_hints={"fps": 2.5, "max_frames": 5},
    )
    assert count == 1
    sqlite_session.refresh(inspection)
    assert inspection.video_duration_ms == 1000
    assert inspection.video_fps == 30.0
    assert inspection.video_codec == "h264"


def test_extract_and_store_frames_honors_frames_bucket_hint(sqlite_session, monkeypatch):
    inspection = Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="raw-b",
        s3_key="raw/a.mp4",
        content_type="video/mp4",
        byte_size=10,
        status=InspectionStatus.queued,
        latitude=None,
        longitude=None,
    )
    sqlite_session.add(inspection)
    sqlite_session.commit()
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"video"))}

    def fake_extract(raw, *, fps, max_frames):
        return (
            [
                frame_extraction.ExtractedFrame(
                    frame_index=0,
                    frame_timestamp_ms=0,
                    image_jpeg=b"jpeg",
                    width=4,
                    height=3,
                )
            ],
            {"video_duration_ms": 1000, "video_fps": 30.0, "video_codec": "h264"},
        )

    monkeypatch.setattr(frame_extraction, "_extract_video_frames", fake_extract)
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="raw-b",
        frames_bucket="default-frames-b",
        aws_region="us-east-1",
        sqs_queue_url="",
    )
    frame_extraction.extract_and_store_frames(
        settings=settings,
        db=sqlite_session,
        s3_client=s3,
        inspection_id=inspection.id,
        extraction_hints={"fps": 2.5, "max_frames": 5, "frames_bucket": "job-frames-b"},
    )
    stored = sqlite_session.query(Frame).filter(Frame.inspection_id == inspection.id).one()
    assert stored.s3_bucket == "job-frames-b"


def test_extract_and_store_frames_records_error_detail(sqlite_session, monkeypatch):
    inspection = Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.mobile,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="raw-b",
        s3_key="raw/a.jpg",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.queued,
        latitude=None,
        longitude=None,
    )
    sqlite_session.add(inspection)
    sqlite_session.commit()
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"not-image"))}

    # Force a deterministic extraction error.
    monkeypatch.setattr(
        frame_extraction,
        "_extract_image_frame",
        MagicMock(side_effect=RuntimeError("decode-failed")),
    )
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="raw-b",
        frames_bucket="frames-b",
        aws_region="us-east-1",
        sqs_queue_url="",
    )
    with pytest.raises(RuntimeError, match="decode-failed"):
        frame_extraction.extract_and_store_frames(
            settings=settings,
            db=sqlite_session,
            s3_client=s3,
            inspection_id=inspection.id,
            extraction_hints={"fps": 1.0, "max_frames": 10},
        )
    sqlite_session.refresh(inspection)
    assert inspection.status == InspectionStatus.frames_failed
    assert inspection.extra_metadata is not None
    assert inspection.extra_metadata.get("frame_extraction_error") == "decode-failed"


def test_run_detection_for_inspection_persists_rows(sqlite_session, monkeypatch):
    inspection = Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="raw-b",
        s3_key="raw/a.jpg",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.frames_extracted,
        frame_count=1,
    )
    sqlite_session.add(inspection)
    sqlite_session.commit()
    frame = Frame(
        id=uuid4(),
        inspection_id=inspection.id,
        frame_index=0,
        frame_timestamp_ms=0,
        s3_bucket="frames-b",
        s3_key="frames/000000.jpg",
        width=10,
        height=10,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
    )
    sqlite_session.add(frame)
    sqlite_session.commit()

    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"img"))}

    class D:
        def __init__(self):
            from app.models.detection import DetectionType

            self.class_name = "tower"
            self.confidence = 0.8
            self.bbox_xmin = 0.1
            self.bbox_ymin = 0.1
            self.bbox_xmax = 0.9
            self.bbox_ymax = 0.9
            self.detection_type = DetectionType.asset
            self.geometry = {"kind": "bbox"}
            self.attributes = {"k": "v"}

    monkeypatch.setattr(
        detection_pipeline,
        "run_frame_detection",
        lambda **kwargs: [D()],
    )
    settings = Settings(database_url="sqlite://", s3_bucket="raw-b", aws_region="us-east-1")
    n = detection_pipeline.run_detection_for_inspection(
        settings=settings,
        db=sqlite_session,
        s3_client=s3,
        inspection_id=inspection.id,
        detection_hints={"threshold": 0.2, "model_name": "yolo", "model_version": "v1"},
    )
    assert n == 1
    rows = sqlite_session.query(Detection).filter(Detection.inspection_id == inspection.id).all()
    assert len(rows) == 1
    sqlite_session.refresh(inspection)
    assert inspection.status == InspectionStatus.detections_ready
    assert inspection.detection_count == 1


def test_run_detection_for_inspection_sets_failed_on_error(sqlite_session, monkeypatch):
    inspection = Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="raw-b",
        s3_key="raw/a.jpg",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.frames_extracted,
        frame_count=1,
    )
    sqlite_session.add(inspection)
    sqlite_session.commit()
    frame = Frame(
        id=uuid4(),
        inspection_id=inspection.id,
        frame_index=0,
        frame_timestamp_ms=0,
        s3_bucket="frames-b",
        s3_key="frames/000000.jpg",
        width=10,
        height=10,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
    )
    sqlite_session.add(frame)
    sqlite_session.commit()

    s3 = MagicMock()
    s3.get_object.side_effect = RuntimeError("s3 failed")
    settings = Settings(database_url="sqlite://", s3_bucket="raw-b", aws_region="us-east-1")
    with pytest.raises(RuntimeError, match="s3 failed"):
        detection_pipeline.run_detection_for_inspection(
            settings=settings,
            db=sqlite_session,
            s3_client=s3,
            inspection_id=inspection.id,
            detection_hints={},
        )
    sqlite_session.refresh(inspection)
    assert inspection.status == InspectionStatus.detections_failed
    assert inspection.extra_metadata is not None
    assert inspection.extra_metadata.get("detection_error") == "s3 failed"


def test_run_detection_for_inspection_honors_enabled_classes(sqlite_session, monkeypatch):
    inspection = Inspection(
        id=uuid4(),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="raw-b",
        s3_key="raw/a.jpg",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.frames_extracted,
        frame_count=1,
    )
    sqlite_session.add(inspection)
    sqlite_session.commit()
    frame = Frame(
        id=uuid4(),
        inspection_id=inspection.id,
        frame_index=0,
        frame_timestamp_ms=0,
        s3_bucket="frames-b",
        s3_key="frames/000000.jpg",
        width=10,
        height=10,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
    )
    sqlite_session.add(frame)
    sqlite_session.commit()

    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"img"))}

    class D:
        def __init__(self, name, det_type):
            self.class_name = name
            self.confidence = 0.8
            self.bbox_xmin = 0.1
            self.bbox_ymin = 0.1
            self.bbox_xmax = 0.9
            self.bbox_ymax = 0.9
            self.detection_type = det_type
            self.geometry = {"kind": "bbox"}
            self.attributes = None

    from app.models.detection import DetectionType

    monkeypatch.setattr(
        detection_pipeline,
        "run_frame_detection",
        lambda **kwargs: [D("tower", DetectionType.asset), D("crack", DetectionType.defect)],
    )
    settings = Settings(database_url="sqlite://", s3_bucket="raw-b", aws_region="us-east-1")
    n = detection_pipeline.run_detection_for_inspection(
        settings=settings,
        db=sqlite_session,
        s3_client=s3,
        inspection_id=inspection.id,
        detection_hints={"enabled_classes": ["tower"]},
    )
    assert n == 1
    rows = sqlite_session.query(Detection).filter(Detection.inspection_id == inspection.id).all()
    assert len(rows) == 1
    assert rows[0].class_name == "tower"

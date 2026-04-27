import json
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_db, get_s3_client, get_sqs_client
from app.core.config import get_settings
from app.db.session import reset_engine
from app.main import app
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus, SourceType


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_happy_path_sets_queued(client, boto_mocks):
    s3, sqs = boto_mocks
    files = {"file": ("clip.mp4", b"\x00\x00\x00\x20ftypmp42", "video/mp4")}
    data = {"source_type": "drone"}
    r = client.post("/ingest/upload", files=files, data=data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["content_type"] == "video/mp4"
    assert body["byte_size"] > 0
    s3.upload_fileobj.assert_called_once()
    sqs.send_message.assert_called_once()
    msg = json.loads(sqs.send_message.call_args.kwargs["MessageBody"])
    assert msg["inspection_id"] == body["id"]
    assert msg["s3_uri"] == f"s3://test-bucket/{body['s3_key']}"


def test_upload_rejects_disallowed_mime(client):
    files = {"file": ("x.bin", b"hello", "application/octet-stream")}
    data = {"source_type": "mobile"}
    r = client.post("/ingest/upload", files=files, data=data)
    assert r.status_code == 415


def test_upload_rejects_oversized(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "5")
    get_settings.cache_clear()
    reset_engine()

    files = {"file": ("big.jpg", b"x" * 20, "image/jpeg")}
    data = {"source_type": "fixed_camera"}
    r = client.post("/ingest/upload", files=files, data=data)
    assert r.status_code == 413

    get_settings.cache_clear()
    reset_engine()


def test_correlation_id_header(client):
    r = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == "abc-123"


def test_json_body_rejected_when_content_length_exceeds_limit(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "120")
    get_settings.cache_clear()
    reset_engine()
    payload = {
        "source_type": "drone",
        "content_type": "image/jpeg",
        "filename": "a.jpg",
        "asset_hint": "x" * 200,
    }
    r = client.post("/ingest/presign", json=payload)
    assert r.status_code == 413
    assert r.headers.get("x-request-id")
    get_settings.cache_clear()
    reset_engine()


def test_presign_returns_502_when_url_generation_fails(sqlite_session, boto_mocks, monkeypatch):
    s3, sqs = boto_mocks
    s3.generate_presigned_url = MagicMock(side_effect=RuntimeError("aws"))
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    get_settings.cache_clear()
    reset_engine()

    def override_db():
        yield sqlite_session

    def override_s3():
        return s3

    def override_sqs():
        return sqs

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_s3_client] = override_s3
    app.dependency_overrides[get_sqs_client] = override_sqs
    try:
        with TestClient(app) as c:
            pr = c.post(
                "/ingest/presign",
                json={
                    "source_type": "drone",
                    "content_type": "image/jpeg",
                    "filename": "a.jpg",
                },
            )
            assert pr.status_code == 502, pr.text
            n = sqlite_session.scalar(select(func.count()).select_from(Inspection)) or 0
            assert n == 0
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        reset_engine()


def test_complete_rejects_s3_content_type_mismatch(sqlite_session, boto_mocks, monkeypatch):
    s3, sqs = boto_mocks
    s3.head_object = MagicMock(
        return_value={"ContentLength": 10, "ContentType": "application/octet-stream"}
    )
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/ingest")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    get_settings.cache_clear()
    reset_engine()

    def override_db():
        yield sqlite_session

    def override_s3():
        return s3

    def override_sqs():
        return sqs

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_s3_client] = override_s3
    app.dependency_overrides[get_sqs_client] = override_sqs
    try:
        with TestClient(app) as c:
            pr = c.post(
                "/ingest/presign",
                json={
                    "source_type": "drone",
                    "content_type": "image/jpeg",
                    "filename": "a.jpg",
                },
            )
            assert pr.status_code == 200, pr.text
            iid = pr.json()["inspection_id"]
            cr = c.post(f"/ingest/{iid}/complete", json={})
            assert cr.status_code == 400
            sqs.send_message.assert_not_called()
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        reset_engine()


def test_complete_rejects_missing_s3_content_type(sqlite_session, boto_mocks, monkeypatch):
    s3, sqs = boto_mocks
    s3.head_object = MagicMock(return_value={"ContentLength": 10})
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/ingest")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    get_settings.cache_clear()
    reset_engine()

    def override_db():
        yield sqlite_session

    def override_s3():
        return s3

    def override_sqs():
        return sqs

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_s3_client] = override_s3
    app.dependency_overrides[get_sqs_client] = override_sqs
    try:
        with TestClient(app) as c:
            pr = c.post(
                "/ingest/presign",
                json={
                    "source_type": "drone",
                    "content_type": "image/jpeg",
                    "filename": "a.jpg",
                },
            )
            assert pr.status_code == 200, pr.text
            iid = pr.json()["inspection_id"]
            cr = c.post(f"/ingest/{iid}/complete", json={})
            assert cr.status_code == 400
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        reset_engine()


def test_presign_and_complete_flow(sqlite_session, boto_mocks, monkeypatch):
    s3, sqs = boto_mocks
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/ingest")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    get_settings.cache_clear()
    reset_engine()

    def override_db():
        yield sqlite_session

    def override_s3():
        return s3

    def override_sqs():
        return sqs

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_s3_client] = override_s3
    app.dependency_overrides[get_sqs_client] = override_sqs
    try:
        with TestClient(app) as c:
            pr = c.post(
                "/ingest/presign",
                json={
                    "source_type": "drone",
                    "content_type": "image/jpeg",
                    "filename": "a.jpg",
                },
            )
            assert pr.status_code == 200, pr.text
            pres = pr.json()
            iid = pres["inspection_id"]
            assert pres["upload_url"].startswith("https://")

            cr = c.post(f"/ingest/{iid}/complete", json={})
            assert cr.status_code == 200, cr.text
            assert cr.json()["status"] == "queued"
            s3.head_object.assert_called()
            sqs.send_message.assert_called()
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        reset_engine()


def test_list_frames_endpoint(client, sqlite_session):
    insp = Inspection(
        id=UUID("4aeb06f3-01ac-45ef-b9f9-c4f3a27287ff"),
        org_id=None,
        source_type=SourceType.drone,
        site_hint="site-a",
        asset_hint="asset-a",
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.frames_extracted,
    )
    sqlite_session.add(insp)
    sqlite_session.commit()
    sqlite_session.add(
        Frame(
            id=UUID("fd73604d-a15c-4cb4-a9ac-b22447ebf61a"),
            inspection_id=insp.id,
            frame_index=0,
            frame_timestamp_ms=0,
            s3_bucket="b",
            s3_key="frames/000000.jpg",
            source_type=SourceType.drone,
            site_hint="site-a",
            asset_hint="asset-a",
        )
    )
    sqlite_session.commit()

    r = client.get(f"/ingest/{insp.id}/frames")
    assert r.status_code == 200
    payload = r.json()
    assert len(payload) == 1
    assert payload[0]["frame_index"] == 0


def test_list_frames_rejects_invalid_pagination(client, sqlite_session):
    insp = Inspection(
        id=UUID("5cd35e8e-6ac7-47ca-8167-58dc8dcdd6f1"),
        org_id=None,
        source_type=SourceType.drone,
        site_hint="site-a",
        asset_hint="asset-a",
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.frames_extracted,
    )
    sqlite_session.add(insp)
    sqlite_session.commit()

    r = client.get(f"/ingest/{insp.id}/frames?limit=0")
    assert r.status_code == 422

    r2 = client.get(f"/ingest/{insp.id}/frames?offset=-1")
    assert r2.status_code == 422


def test_list_detections_filtering(client, sqlite_session):
    insp = Inspection(
        id=UUID("9cf72ed3-5e6c-4d7b-b483-6b2854ad5e6e"),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.detections_ready,
        detection_count=2,
    )
    sqlite_session.add(insp)
    sqlite_session.commit()
    frame = Frame(
        id=UUID("f1ca0f57-1ec7-48b6-9d93-e9e94a833ca1"),
        inspection_id=insp.id,
        frame_index=0,
        frame_timestamp_ms=0,
        s3_bucket="b",
        s3_key="frames/000000.jpg",
        source_type=SourceType.drone,
    )
    sqlite_session.add(frame)
    sqlite_session.commit()
    sqlite_session.add_all(
        [
            Detection(
                id=UUID("53aa9ba5-d413-4385-8897-7dd7e73e65a9"),
                inspection_id=insp.id,
                frame_id=frame.id,
                detection_type=DetectionType.asset,
                class_name="tower",
                confidence=0.9,
                bbox_xmin=0.1,
                bbox_ymin=0.1,
                bbox_xmax=0.8,
                bbox_ymax=0.8,
                geometry={"kind": "bbox"},
                model_name="yolo",
                model_version="v1",
                extra_attributes={"severity": "low"},
            ),
            Detection(
                id=UUID("d08f0453-9df6-4512-a8bc-aa0be8938c0b"),
                inspection_id=insp.id,
                frame_id=frame.id,
                detection_type=DetectionType.defect,
                class_name="crack",
                confidence=0.4,
                bbox_xmin=0.2,
                bbox_ymin=0.2,
                bbox_xmax=0.7,
                bbox_ymax=0.7,
                geometry={"kind": "bbox"},
                model_name="yolo",
                model_version="v1",
            ),
        ]
    )
    sqlite_session.commit()

    r = client.get(
        f"/ingest/{insp.id}/detections?detection_type=asset&min_confidence=0.5&class_name=TOWER"
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] == 1
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["class_name"] == "tower"
    assert payload["items"][0]["geometry"] == {"kind": "bbox"}
    assert payload["items"][0]["attributes"] == {"severity": "low"}


def test_list_frame_detections_endpoint(client, sqlite_session):
    insp = Inspection(
        id=UUID("55e2d9d1-c85b-4360-a711-f7d2f26aeeea"),
        org_id=None,
        source_type=SourceType.drone,
        site_hint=None,
        asset_hint=None,
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=10,
        status=InspectionStatus.detections_ready,
    )
    sqlite_session.add(insp)
    sqlite_session.commit()
    frame = Frame(
        id=UUID("b67c7df9-4742-4e8f-8ea4-6df8fd0ef00b"),
        inspection_id=insp.id,
        frame_index=0,
        frame_timestamp_ms=0,
        s3_bucket="b",
        s3_key="frames/000000.jpg",
        source_type=SourceType.drone,
    )
    sqlite_session.add(frame)
    sqlite_session.commit()
    sqlite_session.add(
        Detection(
            id=UUID("ec22d102-600b-4bca-b82b-f845dbf75f80"),
            inspection_id=insp.id,
            frame_id=frame.id,
            detection_type=DetectionType.environmental_hazard,
            class_name="vegetation_encroachment",
            confidence=0.76,
            bbox_xmin=0.1,
            bbox_ymin=0.1,
            bbox_xmax=0.6,
            bbox_ymax=0.6,
            model_name="yolo",
            model_version="v1",
        )
    )
    sqlite_session.commit()

    r = client.get(f"/ingest/{insp.id}/frames/{frame.id}/detections")
    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["detection_type"] == "environmental_hazard"

import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_db, get_s3_client, get_sqs_client
from app.core.config import get_settings
from app.db.session import reset_engine
from app.main import app
from app.models.inspection import Inspection


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

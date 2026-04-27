from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.core.config import Settings
from app.jobs.publisher import publish_ingest_job
from app.models.inspection import Inspection, InspectionStatus, SourceType
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

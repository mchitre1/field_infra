from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_s3_client, get_sqs_client
from app.core.config import get_settings
from app.db.base import Base
from app.models.alignment import Alignment  # noqa: F401 - register metadata
from app.models.change_event import ChangeEvent  # noqa: F401 - register metadata
from app.models.detection import Detection  # noqa: F401 - register metadata
from app.models.frame import Frame  # noqa: F401 - register metadata
from app.models.inspection import Inspection  # noqa: F401 - register metadata
from app.models.maintenance_recommendation import MaintenanceRecommendation  # noqa: F401 - register metadata
from app.models.risk_rule import RiskRule  # noqa: F401 - register metadata
from app.models.progression_metric import ProgressionMetric  # noqa: F401 - register metadata
from app.db.session import reset_engine
from app.main import app


@pytest.fixture
def boto_mocks() -> tuple[MagicMock, MagicMock]:
    s3 = MagicMock()
    s3.upload_fileobj = MagicMock()
    s3.generate_presigned_url = MagicMock(return_value="https://example.com/presigned-put")
    s3.head_object = MagicMock(
        return_value={"ContentLength": 42, "ContentType": "image/jpeg"}
    )
    sqs = MagicMock()
    sqs.send_message = MagicMock(return_value={"MessageId": "msg-1"})
    return s3, sqs


@pytest.fixture
def sqlite_session() -> Generator[Session, None, None]:
    # StaticPool + check_same_thread=False: TestClient runs the app in a thread;
    # default :memory: SQLite is not visible across threads.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(
    boto_mocks: tuple[MagicMock, MagicMock],
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
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
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    reset_engine()

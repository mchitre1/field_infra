"""FastAPI dependencies: database session and AWS clients for ingest routes."""

from collections.abc import Generator
from typing import Annotated

import boto3
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session


def get_db() -> Generator[Session, None, None]:
    yield from get_session()


def get_s3_client(settings: Annotated[Settings, Depends(get_settings)]):
    return boto3.client("s3", region_name=settings.aws_region)


def get_sqs_client(settings: Annotated[Settings, Depends(get_settings)]):
    return boto3.client("sqs", region_name=settings.aws_region)


DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
S3Client = Annotated[object, Depends(get_s3_client)]
SQSClient = Annotated[object, Depends(get_sqs_client)]

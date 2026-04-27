import argparse
import json
import logging

import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.jobs.messages import IngestJobMessage
from app.services.detection_pipeline import run_detection_for_inspection
from app.services.frame_extraction import extract_and_store_frames

log = logging.getLogger(__name__)


def process_payload(payload: str) -> tuple[int, int]:
    """Run extraction + detection for one job payload.

    Returns: (frame_count, detection_count)
    """
    settings = get_settings()
    msg = IngestJobMessage.model_validate_json(payload)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    s3 = boto3.client("s3", region_name=settings.aws_region)
    with Session(engine) as db:
        count = extract_and_store_frames(
            settings=settings,
            db=db,
            s3_client=s3,
            inspection_id=msg.inspection_id,
            extraction_hints=msg.frame_extraction,
        )
        detection_count = run_detection_for_inspection(
            settings=settings,
            db=db,
            s3_client=s3,
            inspection_id=msg.inspection_id,
            detection_hints=msg.detection,
        )
    return count, detection_count


def main() -> None:
    """CLI entrypoint for local worker execution with a JSON job payload."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="IIE ingest frame extraction worker")
    parser.add_argument("payload", nargs="?", help="JSON ingest job body")
    args = parser.parse_args()
    if not args.payload:
        log.info("No payload provided")
        return
    payload = args.payload
    if payload.startswith("{"):
        body = payload
    else:
        body = json.dumps(json.loads(payload))
    frame_count, detection_count = process_payload(body)
    log.info(
        "Completed worker run: extracted %s frames, persisted %s detections",
        frame_count,
        detection_count,
    )


if __name__ == "__main__":
    main()

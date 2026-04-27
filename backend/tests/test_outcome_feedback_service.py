import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.models.outcome_feedback import OutcomeFeedback
from app.schemas.outcomes import OutcomeSubmitRequest
from app.services.issue_state_service import org_scope_for
from app.services.outcome_feedback_service import (
    list_outcome_feedback,
    submit_outcome_feedback,
    zone_feedback_score_adjustment,
)


def test_submit_resolves_issue_key_from_detection_fields(sqlite_session: Session):
    body = OutcomeSubmitRequest(
        asset_zone_id="z1",
        detection_type="defect",
        class_name="Crack",
        outcome_kind="general",
        outcome_code="confirmed",
    )
    row = submit_outcome_feedback(db=sqlite_session, body=body)
    assert row.issue_key == "defect:crack:default"


def test_submit_invalid_code_for_kind_422(sqlite_session: Session):
    body = OutcomeSubmitRequest(
        asset_zone_id="z1",
        issue_key="defect:crack:default",
        outcome_kind="general",
        outcome_code="false_positive",
    )
    with pytest.raises(HTTPException) as exc:
        submit_outcome_feedback(db=sqlite_session, body=body)
    assert exc.value.status_code == 422


def test_list_without_org_id_returns_only_global_scope(sqlite_session: Session):
    org = uuid.uuid4()
    sqlite_session.add(
        OutcomeFeedback(
            id=uuid.uuid4(),
            actor="a",
            org_scope="global",
            org_id=None,
            asset_zone_id="oz-shared",
            issue_key="defect:crack:default",
            outcome_kind="general",
            outcome_code="confirmed",
            created_at=datetime.now(timezone.utc),
        )
    )
    sqlite_session.add(
        OutcomeFeedback(
            id=uuid.uuid4(),
            actor="b",
            org_scope=org_scope_for(org),
            org_id=org,
            asset_zone_id="oz-shared",
            issue_key="defect:crack:default",
            outcome_kind="general",
            outcome_code="other",
            created_at=datetime.now(timezone.utc),
        )
    )
    sqlite_session.commit()
    rows, total = list_outcome_feedback(db=sqlite_session, asset_zone_id="oz-shared")
    assert total == 1
    assert rows[0].org_id is None


def test_submit_primary_detection_must_match_target_inspection(sqlite_session: Session):
    insp_a = uuid.uuid4()
    insp_b = uuid.uuid4()
    fid = uuid.uuid4()
    sqlite_session.add_all(
        [
            Inspection(
                id=insp_a,
                org_id=None,
                source_type=SourceType.drone,
                site_hint="s",
                asset_hint="a",
                capture_timestamp=None,
                s3_bucket="b",
                s3_key="ka",
                content_type="image/jpeg",
                byte_size=1,
                status=InspectionStatus.alignment_ready,
            ),
            Inspection(
                id=insp_b,
                org_id=None,
                source_type=SourceType.drone,
                site_hint="s",
                asset_hint="a",
                capture_timestamp=None,
                s3_bucket="b",
                s3_key="kb",
                content_type="image/jpeg",
                byte_size=1,
                status=InspectionStatus.alignment_ready,
            ),
        ]
    )
    sqlite_session.commit()
    sqlite_session.add(
        Frame(
            id=fid,
            inspection_id=insp_a,
            frame_index=0,
            frame_timestamp_ms=0,
            s3_bucket="b",
            s3_key="f.jpg",
            source_type=SourceType.drone,
        )
    )
    sqlite_session.commit()
    det_id = uuid.uuid4()
    sqlite_session.add(
        Detection(
            id=det_id,
            inspection_id=insp_a,
            frame_id=fid,
            detection_type=DetectionType.defect,
            class_name="crack",
            confidence=0.9,
            bbox_xmin=0.0,
            bbox_ymin=0.0,
            bbox_xmax=0.1,
            bbox_ymax=0.1,
            geometry=None,
            model_name="yolo",
            model_version="v1",
            asset_zone_hint="z",
        )
    )
    sqlite_session.commit()
    body = OutcomeSubmitRequest(
        asset_zone_id="z",
        issue_key="defect:crack:default",
        outcome_kind="model_label",
        outcome_code="false_positive",
        target_inspection_id=insp_b,
        primary_detection_id=det_id,
    )
    with pytest.raises(HTTPException) as exc:
        submit_outcome_feedback(db=sqlite_session, body=body)
    assert exc.value.status_code == 422


def test_submit_target_inspection_missing_404(sqlite_session: Session):
    missing = uuid.uuid4()
    body = OutcomeSubmitRequest(
        asset_zone_id="z1",
        issue_key="defect:crack:default",
        outcome_kind="model_label",
        outcome_code="false_positive",
        target_inspection_id=missing,
    )
    with pytest.raises(HTTPException) as exc:
        submit_outcome_feedback(db=sqlite_session, body=body)
    assert exc.value.status_code == 404


def test_zone_feedback_adjustment_after_threshold(sqlite_session: Session):
    org = uuid.uuid4()
    scope = org_scope_for(org)
    zone = "hot-zone"
    ikey = "defect:crack:default"
    for _ in range(3):
        sqlite_session.add(
            OutcomeFeedback(
                id=uuid.uuid4(),
                actor="t",
                org_scope=scope,
                org_id=org,
                asset_zone_id=zone,
                issue_key=ikey,
                outcome_kind="risk_priority",
                outcome_code="priority_too_high",
                created_at=datetime.now(timezone.utc),
            )
        )
    sqlite_session.commit()

    insp = Inspection(
        id=uuid.uuid4(),
        org_id=org,
        source_type=SourceType.drone,
        site_hint="s",
        asset_hint="a",
        capture_timestamp=None,
        s3_bucket="b",
        s3_key="k",
        content_type="image/jpeg",
        byte_size=1,
        status=InspectionStatus.alignment_ready,
    )
    settings = Settings().model_copy(
        update={
            "feedback_score_enabled": True,
            "feedback_score_min_samples": 3,
            "feedback_score_max_delta": 10.0,
            "feedback_score_step": 1.5,
            "feedback_score_lookback_days": 90,
        }
    )

    fid = uuid.uuid4()
    sqlite_session.add(
        Frame(
            id=fid,
            inspection_id=insp.id,
            frame_index=0,
            frame_timestamp_ms=0,
            s3_bucket="b",
            s3_key="f.jpg",
            source_type=SourceType.drone,
        )
    )
    det = Detection(
        id=uuid.uuid4(),
        inspection_id=insp.id,
        frame_id=fid,
        detection_type=DetectionType.defect,
        class_name="crack",
        confidence=0.9,
        bbox_xmin=0.0,
        bbox_ymin=0.0,
        bbox_xmax=0.1,
        bbox_ymax=0.1,
        geometry=None,
        model_name="yolo",
        model_version="v1",
        asset_zone_hint=zone,
    )
    sqlite_session.add_all([insp, det])
    sqlite_session.commit()

    adj, factors = zone_feedback_score_adjustment(
        db=sqlite_session,
        settings=settings,
        inspection=insp,
        zone_id=zone,
        zone_detections=[det],
    )
    assert adj < 0
    assert factors and factors[0].get("kind") == "operator_feedback"

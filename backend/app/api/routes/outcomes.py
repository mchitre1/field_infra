"""Operator outcome feedback for model export and risk-score priors."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.outcomes import OutcomeFeedbackPublic, OutcomeListResponse, OutcomeSubmitRequest
from app.services.outcome_feedback_service import list_outcome_feedback, submit_outcome_feedback

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.post("", response_model=OutcomeFeedbackPublic, status_code=201)
def post_outcome(db: DbSession, body: OutcomeSubmitRequest) -> OutcomeFeedbackPublic:
    row = submit_outcome_feedback(db=db, body=body)
    return OutcomeFeedbackPublic.model_validate(row)


@router.get("", response_model=OutcomeListResponse)
def get_outcomes(
    db: DbSession,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    org_id: UUID | None = None,
    asset_zone_id: str | None = None,
    issue_key: str | None = None,
    outcome_kind: str | None = None,
    target_inspection_id: UUID | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> OutcomeListResponse:
    rows, total = list_outcome_feedback(
        db=db,
        created_from=created_from,
        created_to=created_to,
        org_id=org_id,
        asset_zone_id=asset_zone_id,
        issue_key=issue_key,
        outcome_kind=outcome_kind,
        target_inspection_id=target_inspection_id,
        model_name=model_name,
        model_version=model_version,
        limit=limit,
        offset=offset,
    )
    return OutcomeListResponse(
        items=[OutcomeFeedbackPublic.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )

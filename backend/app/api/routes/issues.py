"""Issue workflow state (fixed, monitoring, deferred, ignored)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession
from app.schemas.issues import IssueListResponse, IssuePublic, IssueStateEventPublic, IssueUpsertRequest
from app.services.issue_key import build_issue_key
from app.services.issue_state_service import list_issue_states, upsert_issue_state

router = APIRouter(prefix="/issues", tags=["issues"])


def _resolve_issue_key(body: IssueUpsertRequest) -> str:
    if body.issue_key and body.issue_key.strip():
        return body.issue_key.strip()
    if (
        body.detection_type
        and body.detection_type.strip()
        and body.class_name
        and body.class_name.strip()
    ):
        return build_issue_key(body.detection_type, body.class_name, subtype=body.subtype)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Provide issue_key or both detection_type and class_name",
    )


@router.put("/state", response_model=IssuePublic, status_code=status.HTTP_200_OK)
def put_issue_state(db: DbSession, body: IssueUpsertRequest) -> IssuePublic:
    """Create or update issue state for ``(org_scope, asset_zone_id, issue_key)``."""
    key = _resolve_issue_key(body)
    row = upsert_issue_state(
        db=db,
        org_id=body.org_id,
        asset_zone_id=body.asset_zone_id,
        issue_key=key,
        state=body.state,
        notes=body.notes,
        updated_by=body.updated_by,
        last_target_inspection_id=body.last_target_inspection_id,
    )
    return IssuePublic(
        id=row.id,
        org_id=row.org_id,
        asset_zone_id=row.asset_zone_id,
        issue_key=row.issue_key,
        state=row.state,
        notes=row.notes,
        updated_by=row.updated_by,
        last_target_inspection_id=row.last_target_inspection_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        events=[],
    )


@router.get("", response_model=IssueListResponse)
def get_issues(
    db: DbSession,
    org_id: UUID | None = None,
    asset_zone_id: str | None = None,
    state: str | None = None,
    include_events: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> IssueListResponse:
    rows, total = list_issue_states(
        db=db,
        org_id=org_id,
        asset_zone_id=asset_zone_id,
        state=state,
        include_events=include_events,
        limit=limit,
        offset=offset,
    )
    items: list[IssuePublic] = []
    for r in rows:
        evs = (
            [IssueStateEventPublic.model_validate(e) for e in r.events]
            if include_events
            else []
        )
        items.append(
            IssuePublic(
                id=r.id,
                org_id=r.org_id,
                asset_zone_id=r.asset_zone_id,
                issue_key=r.issue_key,
                state=r.state,
                notes=r.notes,
                updated_by=r.updated_by,
                last_target_inspection_id=r.last_target_inspection_id,
                created_at=r.created_at,
                updated_at=r.updated_at,
                events=evs,
            )
        )
    return IssueListResponse(items=items, total=total, limit=limit, offset=offset)

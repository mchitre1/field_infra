import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inspection import Inspection, InspectionStatus, SourceType
from app.models.issue_state import IssueStateEvent
from app.services.issue_state_service import list_issue_states, upsert_issue_state


def test_upsert_creates_and_updates_emits_events(sqlite_session: Session):
    iid = uuid.uuid4()
    sqlite_session.add(
        Inspection(
            id=iid,
            org_id=None,
            source_type=SourceType.drone,
            site_hint="s",
            asset_hint="a",
            capture_timestamp=None,
            s3_bucket="b",
            s3_key="k",
            content_type="image/jpeg",
            byte_size=10,
            status=InspectionStatus.alignment_ready,
        )
    )
    sqlite_session.commit()

    row = upsert_issue_state(
        db=sqlite_session,
        org_id=None,
        asset_zone_id="zone-1",
        issue_key="defect:crack:default",
        state="monitoring",
        notes="watch",
        updated_by="ops@example.com",
        last_target_inspection_id=iid,
    )
    assert row.state == "monitoring"
    n_ev = sqlite_session.scalar(select(func.count()).select_from(IssueStateEvent)) or 0
    assert n_ev == 1

    row2 = upsert_issue_state(
        db=sqlite_session,
        org_id=None,
        asset_zone_id="zone-1",
        issue_key="defect:crack:default",
        state="fixed",
        notes="done",
        updated_by="ops@example.com",
        last_target_inspection_id=None,
    )
    assert row2.id == row.id
    assert row2.state == "fixed"
    n_ev2 = sqlite_session.scalar(select(func.count()).select_from(IssueStateEvent)) or 0
    assert n_ev2 == 2


def test_list_without_org_id_returns_only_global_scope(sqlite_session: Session):
    upsert_issue_state(
        db=sqlite_session,
        org_id=None,
        asset_zone_id="shared-zone",
        issue_key="defect:crack:default",
        state="monitoring",
        notes=None,
        updated_by=None,
        last_target_inspection_id=None,
    )
    oid = uuid.uuid4()
    upsert_issue_state(
        db=sqlite_session,
        org_id=oid,
        asset_zone_id="shared-zone",
        issue_key="defect:crack:default",
        state="deferred",
        notes=None,
        updated_by=None,
        last_target_inspection_id=None,
    )
    rows, total = list_issue_states(
        db=sqlite_session, org_id=None, asset_zone_id="shared-zone"
    )
    assert total == 1
    assert rows[0].org_id is None
    assert rows[0].state == "monitoring"


def test_list_filters_org_and_state(sqlite_session: Session):
    upsert_issue_state(
        db=sqlite_session,
        org_id=None,
        asset_zone_id="z-a",
        issue_key="k1",
        state="deferred",
        notes=None,
        updated_by=None,
        last_target_inspection_id=None,
    )
    oid = uuid.uuid4()
    upsert_issue_state(
        db=sqlite_session,
        org_id=oid,
        asset_zone_id="z-b",
        issue_key="k2",
        state="ignored",
        notes=None,
        updated_by=None,
        last_target_inspection_id=None,
    )
    rows, total = list_issue_states(db=sqlite_session, org_id=oid, state="ignored")
    assert total == 1
    assert rows[0].issue_key == "k2"


def test_upsert_invalid_state_raises(sqlite_session: Session):
    with pytest.raises(HTTPException) as exc:
        upsert_issue_state(
            db=sqlite_session,
            org_id=None,
            asset_zone_id="z",
            issue_key="k",
            state="nope",
            notes=None,
            updated_by=None,
            last_target_inspection_id=None,
        )
    assert exc.value.status_code == 422

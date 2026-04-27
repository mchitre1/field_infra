from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.zone_decision_log_service import list_zone_decision_log


def test_put_issue_state_writes_zone_decision_log(client: TestClient, sqlite_session: Session):
    zone = f"site-{uuid4().hex[:8]}:crack:1:2"
    r = client.put(
        "/issues/state",
        json={
            "asset_zone_id": zone,
            "issue_key": "defect:crack:default",
            "state": "monitoring",
        },
    )
    assert r.status_code == 200, r.text
    rows, total = list_zone_decision_log(db=sqlite_session, asset_zone_id=zone)
    assert total >= 1
    assert any(x.event_type == "issue_state_transition" for x in rows)


def test_post_outcome_writes_zone_decision_log(client: TestClient, sqlite_session: Session):
    zone = f"out-{uuid4().hex[:8]}"
    r = client.post(
        "/outcomes",
        json={
            "asset_zone_id": zone,
            "issue_key": "defect:rust:default",
            "outcome_kind": "general",
            "outcome_code": "confirmed",
        },
    )
    assert r.status_code == 201, r.text
    rows, total = list_zone_decision_log(db=sqlite_session, asset_zone_id=zone)
    assert total >= 1
    assert any(x.event_type == "operator_outcome" for x in rows)


def test_get_zone_decision_log_http(client: TestClient):
    zone = f"http-{uuid4().hex[:8]}"
    client.put(
        "/issues/state",
        json={"asset_zone_id": zone, "issue_key": "defect:crack:default", "state": "ignored"},
    )
    lr = client.get("/ingest/zone-decision-log", params={"asset_zone_id": zone})
    assert lr.status_code == 200
    data = lr.json()
    assert data["total"] >= 1
    assert data["items"][0]["event_type"] == "issue_state_transition"


def test_get_inspection_history_http(client: TestClient, sqlite_session: Session):
    from app.models.inspection import Inspection, InspectionStatus, SourceType
    from app.services.inspection_history_service import record_inspection_status_transition

    iid = uuid4()
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
            byte_size=1,
            status=InspectionStatus.received,
        )
    )
    sqlite_session.commit()
    record_inspection_status_transition(
        db=sqlite_session,
        inspection_id=iid,
        from_status=InspectionStatus.received,
        to_status=InspectionStatus.stored,
        source="test",
        context=None,
    )
    sqlite_session.commit()
    r = client.get("/ingest/inspection-history", params={"inspection_id": str(iid)})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert body["items"][0]["from_status"] == "received"
    assert body["items"][0]["to_status"] == "stored"

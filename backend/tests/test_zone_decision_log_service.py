import uuid

from sqlalchemy.orm import Session

from app.services.zone_decision_log_service import append_zone_decision_log, list_zone_decision_log


def test_append_and_list_zone_decision_log(sqlite_session: Session):
    oid = uuid.uuid4()
    append_zone_decision_log(
        db=sqlite_session,
        org_id=oid,
        asset_zone_id="zone-a",
        event_type="operator_outcome",
        issue_key="defect:x:default",
        inspection_id=None,
        payload={"summary": "test", "refs": {}},
    )
    sqlite_session.commit()
    rows, total = list_zone_decision_log(db=sqlite_session, asset_zone_id="zone-a", org_id=oid)
    assert total == 1
    assert rows[0].event_type == "operator_outcome"

    append_zone_decision_log(
        db=sqlite_session,
        org_id=None,
        asset_zone_id="zone-a",
        event_type="note",
        issue_key=None,
        inspection_id=None,
        payload={"summary": "global", "refs": {}},
    )
    sqlite_session.commit()
    rows2, total2 = list_zone_decision_log(db=sqlite_session, asset_zone_id="zone-a")
    assert total2 == 1
    assert rows2[0].event_type == "note"

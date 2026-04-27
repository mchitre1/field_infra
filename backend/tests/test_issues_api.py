from uuid import UUID

from fastapi.testclient import TestClient


def test_put_issue_state_and_list(client: TestClient):
    body = {
        "asset_zone_id": "site-x:crack:1:2",
        "issue_key": "defect:crack:default",
        "state": "monitoring",
        "notes": "n1",
        "updated_by": "u1",
    }
    r = client.put("/issues/state", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["state"] == "monitoring"
    assert data["asset_zone_id"] == "site-x:crack:1:2"

    r2 = client.put(
        "/issues/state",
        json={
            "asset_zone_id": "site-x:crack:1:2",
            "detection_type": "defect",
            "class_name": "crack",
            "state": "fixed",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["state"] == "fixed"

    lr = client.get("/issues", params={"asset_zone_id": "site-x:crack:1:2"})
    assert lr.status_code == 200
    assert lr.json()["total"] >= 1

    ev = client.get("/issues", params={"asset_zone_id": "site-x:crack:1:2", "include_events": "true"})
    assert ev.status_code == 200
    assert len(ev.json()["items"][0]["events"]) >= 2


def test_put_issue_state_invalid_returns_422(client: TestClient):
    r = client.put(
        "/issues/state",
        json={"asset_zone_id": "z", "issue_key": "k", "state": "unknown"},
    )
    assert r.status_code == 422

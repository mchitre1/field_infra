from fastapi.testclient import TestClient


def test_post_outcome_and_list(client: TestClient):
    r = client.post(
        "/outcomes",
        json={
            "asset_zone_id": "site-a:zone",
            "issue_key": "defect:rust:default",
            "outcome_kind": "model_label",
            "outcome_code": "false_positive",
            "actor": "ops-1",
            "notes": "shadow",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["issue_key"] == "defect:rust:default"
    assert data["outcome_code"] == "false_positive"
    assert data["actor"] == "ops-1"

    lr = client.get("/outcomes", params={"asset_zone_id": "site-a:zone", "limit": 50})
    assert lr.status_code == 200
    body = lr.json()
    assert body["total"] >= 1
    assert any(x["id"] == data["id"] for x in body["items"])


def test_post_outcome_invalid_kind_422(client: TestClient):
    r = client.post(
        "/outcomes",
        json={
            "asset_zone_id": "z",
            "issue_key": "k",
            "outcome_kind": "not_a_kind",
            "outcome_code": "other",
        },
    )
    assert r.status_code == 422

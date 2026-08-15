import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RELIEFLINK_DB", str(tmp_path / "test.db"))
    import app.main
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def post_req(client, text, lat=13.0, lon=80.2):
    return client.post("/api/requests", json={"text": text, "lat": lat, "lon": lon})


def test_create_request_is_triaged(client):
    res = post_req(client, "trapped on roof, water rising, 4 people")
    assert res.status_code == 201
    r = res.json()["request"]
    assert r["category"] == "rescue" and r["level"] == "CRITICAL" and r["people"] == 4


def test_invalid_coordinates_rejected(client):
    assert client.post("/api/requests", json={"text": "help", "lat": 200, "lon": 80}).status_code == 422


def test_duplicate_is_merged(client):
    first = post_req(client, "family trapped on terrace, water rising").json()["request"]
    second = post_req(client, "Family stuck on terrace, water rising fast", lat=13.0005, lon=80.2003).json()
    assert second["duplicate_of"] == first["id"]
    assert second["request"]["report_count"] == 2
    detail = client.get(f"/api/requests/{first['id']}").json()
    assert len(detail["reports"]) == 2
    assert client.get("/api/stats").json()["duplicates_merged"] == 1


def test_list_sorted_by_urgency(client):
    post_req(client, "need blankets", lat=13.1)
    post_req(client, "child drowning, water rising", lat=13.2)
    post_req(client, "need food for 3 people", lat=13.3)
    levels = [r["effective_urgency"] for r in client.get("/api/requests").json()]
    assert levels == sorted(levels, reverse=True)


def test_sms_intake(client):
    ok = client.post("/api/sms", json={"sender": "98400", "body": "HELP trapped with 2 kids @13.04,80.25"}).json()
    assert ok["accepted"] and ("CRITICAL" in ok["reply"] or "HIGH" in ok["reply"])
    missing = client.post("/api/sms", json={"sender": "98400", "body": "help please"}).json()
    assert not missing["accepted"] and "location" in missing["reply"]


def test_volunteer_skill_validation(client):
    bad = client.post("/api/volunteers", json={"name": "x", "skills": ["flying"], "lat": 13, "lon": 80})
    assert bad.status_code == 422


def test_dispatch_and_resolve_flow(client):
    client.post("/api/volunteers", json={"name": "Boat", "skills": ["rescue"], "lat": 13.0, "lon": 80.2})
    rid = post_req(client, "trapped on roof, water rising").json()["request"]["id"]
    post_req(client, "need food", lat=13.01)  # no supplies volunteer: stays open

    d = client.post("/api/dispatch").json()
    assert d["assigned"] == 1 and d["plan"][0]["request_id"] == rid
    assert client.get(f"/api/requests/{rid}").json()["status"] == "assigned"
    assert len(client.get("/api/assignments").json()) == 1

    # Volunteer is now busy, so a second dispatch assigns nothing.
    assert client.post("/api/dispatch").json()["assigned"] == 0

    client.post(f"/api/requests/{rid}/resolve")
    assert client.get(f"/api/requests/{rid}").json()["status"] == "resolved"
    assert client.get("/api/assignments").json() == []


def test_dry_run_saves_nothing(client):
    client.post("/api/volunteers", json={"name": "Boat", "skills": ["rescue"], "lat": 13.0, "lon": 80.2})
    post_req(client, "trapped on roof")
    assert client.post("/api/dispatch?dry_run=true").json()["assigned"] == 1
    assert client.get("/api/assignments").json() == []


def test_demo_seed_and_compare(client):
    seeded = client.post("/api/demo/seed").json()
    assert seeded["duplicates_merged"] >= 2
    cmp = client.get("/api/dispatch/compare").json()
    assert cmp["optimal"]["urgency_served"] >= cmp["greedy"]["urgency_served"]


def test_dashboard_served(client):
    res = client.get("/")
    assert res.status_code == 200 and "ReliefLink" in res.text


def test_unrecognized_request_flagged_and_reviewable(client):
    r = post_req(client, "please call my number, urgent situation").json()["request"]
    assert r["needs_review"] == 1
    assert client.get("/api/stats").json()["needs_review"] == 1

    reviewed = client.post(f"/api/requests/{r['id']}/review?category=medical&urgency=80").json()
    assert reviewed["needs_review"] == 0
    assert reviewed["category"] == "medical" and reviewed["level"] == "CRITICAL"
    assert client.post(f"/api/requests/{r['id']}/review?category=flying").status_code == 400

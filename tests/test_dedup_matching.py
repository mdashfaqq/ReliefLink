from app.dedup import find_duplicate
from app.matching import greedy_dispatch, optimal_dispatch, summarize

NOW = "2026-01-01T10:00:00+00:00"


def req(id, urgency, category, lat, lon, created=NOW):
    return {"id": id, "urgency": urgency, "category": category, "lat": lat, "lon": lon, "created_at": created}


def vol(id, skills, lat, lon, capacity=1):
    return {"id": id, "skills": skills, "lat": lat, "lon": lon, "capacity": capacity}


# ---------------- dedup

def test_same_incident_nearby_is_duplicate():
    existing = {"id": 1, "text": "family trapped on terrace water rising", "lat": 13.0, "lon": 80.2,
                "needs": ["rescue"], "created_at": NOW}
    new = {"text": "Family stuck on the terrace, water rising!", "lat": 13.0008, "lon": 80.2005,
           "needs": ["rescue"], "created_at": NOW}
    match = find_duplicate(new, [existing])
    assert match and match[0]["id"] == 1


def test_far_away_is_not_duplicate():
    existing = {"id": 1, "text": "family trapped on terrace", "lat": 13.0, "lon": 80.2,
                "needs": ["rescue"], "created_at": NOW}
    new = dict(existing, lat=13.05, lon=80.25)  # ~7 km away
    new.pop("id")
    assert find_duplicate(new, [existing]) is None


def test_different_need_is_not_duplicate():
    existing = {"id": 1, "text": "need food here", "lat": 13.0, "lon": 80.2, "needs": ["food"], "created_at": NOW}
    new = {"text": "need a doctor here", "lat": 13.0, "lon": 80.2, "needs": ["medical"], "created_at": NOW}
    assert find_duplicate(new, [existing]) is None


def test_old_report_is_not_duplicate():
    existing = {"id": 1, "text": "trapped on terrace", "lat": 13.0, "lon": 80.2, "needs": ["rescue"],
                "created_at": "2026-01-01T08:00:00+00:00"}
    new = {"text": "trapped on terrace", "lat": 13.0, "lon": 80.2, "needs": ["rescue"],
           "created_at": "2026-01-02T08:00:00+00:00"}
    assert find_duplicate(new, [existing]) is None


# ---------------- matching

def test_skill_constraint_respected():
    vols = [vol(1, ["supplies"], 13.0, 80.2)]
    reqs = [req(10, 90, "medical", 13.0, 80.2)]
    assert optimal_dispatch(vols, reqs) == []


def test_capacity_respected():
    vols = [vol(1, ["supplies"], 13.0, 80.2, capacity=2)]
    reqs = [req(i, 40, "food", 13.0 + i * 0.001, 80.2) for i in range(5)]
    plan = optimal_dispatch(vols, reqs)
    assert len(plan) == 2
    assert all(a.volunteer_id == 1 for a in plan)


def test_optimal_prefers_urgent_over_old():
    # One boat. An older low-urgency request and a newer critical one.
    vols = [vol(1, ["rescue"], 13.0, 80.2)]
    reqs = [req(1, 36, "rescue", 13.001, 80.2, created="2026-01-01T09:00:00+00:00"),
            req(2, 95, "rescue", 13.005, 80.2, created="2026-01-01T09:30:00+00:00")]
    assert [a.request_id for a in optimal_dispatch(vols, reqs)] == [2]
    # The first-come baseline serves the older, less urgent one.
    assert [a.request_id for a in greedy_dispatch(vols, reqs)] == [1]


def test_optimal_avoids_long_trips_when_possible():
    # Two medics, two patients. Crossing assignments would double the travel.
    vols = [vol(1, ["medical"], 13.00, 80.20), vol(2, ["medical"], 13.10, 80.20)]
    reqs = [req(10, 60, "medical", 13.10, 80.201), req(11, 60, "medical", 13.00, 80.201)]
    plan = {a.request_id: a.volunteer_id for a in optimal_dispatch(vols, reqs)}
    assert plan == {10: 2, 11: 1}


def test_too_far_is_infeasible():
    vols = [vol(1, ["rescue"], 13.0, 80.2)]
    reqs = [req(1, 99, "rescue", 14.0, 80.2)]  # ~110 km
    assert optimal_dispatch(vols, reqs) == []


def test_summary_counts_critical():
    vols = [vol(1, ["rescue"], 13.0, 80.2)]
    reqs = [req(1, 80, "rescue", 13.0, 80.2), req(2, 75, "rescue", 13.0, 80.21)]
    s = summarize(optimal_dispatch(vols, reqs), reqs)
    assert s["critical_total"] == 2 and s["critical_served"] == 1

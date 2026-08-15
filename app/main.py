"""ReliefLink API.

Run:   uvicorn app.main:app --reload
Open:  http://127.0.0.1:8000        (coordinator dashboard)
Docs:  http://127.0.0.1:8000/docs   (interactive API)
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import db
from .dedup import find_duplicate
from .geo import valid_coords
from .matching import SKILL_FOR_NEED, greedy_dispatch, optimal_dispatch, summarize
from .triage import level_for, triage

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
VALID_SKILLS = sorted(set(SKILL_FOR_NEED.values()))

# Waiting time slowly raises priority so low-urgency requests are never starved.
AGING_POINTS_PER_HOUR = 6
AGING_CAP = 15


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="ReliefLink", version="1.0", lifespan=lifespan,
              description="AI-assisted disaster relief coordination: triage, de-duplication and optimal dispatch.")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------- schemas

class RequestIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=1000)
    lat: float
    lon: float
    contact: str | None = Field(None, max_length=40)
    source: str = Field("web", pattern=r"^(web|sms|whatsapp|helpline|social)$")

    @field_validator("lon")
    @classmethod
    def coords_ok(cls, lon, info):
        lat = info.data.get("lat")
        if lat is None or not valid_coords(lat, lon):
            raise ValueError("invalid coordinates")
        return lon


class VolunteerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    phone: str | None = Field(None, max_length=20)
    skills: list[str] = Field(..., min_length=1)
    lat: float
    lon: float
    capacity: int = Field(1, ge=1, le=10)

    @field_validator("skills")
    @classmethod
    def skills_ok(cls, skills):
        bad = set(skills) - set(VALID_SKILLS)
        if bad:
            raise ValueError(f"unknown skills {sorted(bad)}; valid: {VALID_SKILLS}")
        return sorted(set(skills))


class SmsIn(BaseModel):
    sender: str = Field(..., max_length=20)
    body: str = Field(..., max_length=500)


class TriagePreview(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


# ---------------------------------------------------------------- helpers

def effective_urgency(req: dict, now: datetime | None = None) -> int:
    if req["status"] != "open":
        return req["urgency"]
    now = now or datetime.now(timezone.utc)
    hours = (now - datetime.fromisoformat(req["created_at"])).total_seconds() / 3600
    return min(100, req["urgency"] + min(AGING_CAP, int(hours * AGING_POINTS_PER_HOUR)))


def decorate(req: dict) -> dict:
    req["effective_urgency"] = effective_urgency(req)
    req["effective_level"] = level_for(req["effective_urgency"])
    return req


def create_or_merge(body: RequestIn) -> dict:
    """Triage a new message, merge it into an existing incident if it's a duplicate."""
    t = triage(body.text)
    now = db.now_iso()
    new = {"text": body.text, "lat": body.lat, "lon": body.lon, "needs": t.needs, "created_at": now}

    with db.connect() as conn:
        open_reqs = db.rows(conn, "SELECT * FROM requests WHERE status != 'resolved'")
        dup = find_duplicate(new, open_reqs)
        if dup:
            existing, similarity = dup
            count = existing["report_count"] + 1
            # Re-triage the combined evidence: a second report may reveal new details.
            combined = triage(existing["text"] + " . " + body.text, report_count=count)
            urgency = max(existing["urgency"], combined.urgency)
            needs = list(dict.fromkeys(existing["needs"] + combined.needs))
            conn.execute(
                "UPDATE requests SET report_count=?, urgency=?, level=?, needs=?, reasons=?, "
                "people=max(people, ?), needs_review=?, updated_at=? WHERE id=?",
                (count, urgency, level_for(urgency), json.dumps(needs), json.dumps(combined.reasons),
                 combined.people, int(combined.needs_review), now, existing["id"]),
            )
            conn.execute("INSERT INTO reports (request_id, text, source, created_at) VALUES (?,?,?,?)",
                         (existing["id"], body.text, body.source, now))
            merged = db.row_to_dict(conn.execute("SELECT * FROM requests WHERE id=?", (existing["id"],)).fetchone())
            return {"request": decorate(merged), "duplicate_of": existing["id"], "similarity": similarity}

        cur = conn.execute(
            "INSERT INTO requests (text, lat, lon, contact, source, language, category, needs, urgency, "
            "level, people, reasons, needs_review, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (body.text, body.lat, body.lon, body.contact, body.source, t.language, t.category,
             json.dumps(t.needs), t.urgency, t.level, t.people, json.dumps(t.reasons), int(t.needs_review), now, now),
        )
        conn.execute("INSERT INTO reports (request_id, text, source, created_at) VALUES (?,?,?,?)",
                     (cur.lastrowid, body.text, body.source, now))
        created = db.row_to_dict(conn.execute("SELECT * FROM requests WHERE id=?", (cur.lastrowid,)).fetchone())
        return {"request": decorate(created), "duplicate_of": None}


def load_dispatch_inputs(conn):
    requests = [decorate(r) for r in db.rows(conn, "SELECT * FROM requests WHERE status='open'")]
    volunteers = db.rows(conn, """
        SELECT v.*, v.capacity - COUNT(a.id) AS remaining
        FROM volunteers v LEFT JOIN assignments a ON a.volunteer_id = v.id AND a.status = 'active'
        WHERE v.active = 1 GROUP BY v.id HAVING remaining > 0""")
    for v in volunteers:
        v["capacity"] = v["remaining"]
    # The optimizer should see the aged urgency so long-waiting requests move up.
    for r in requests:
        r["urgency"] = r["effective_urgency"]
    return volunteers, requests


# ---------------------------------------------------------------- routes

@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/triage")
def triage_preview(body: TriagePreview):
    """Score a message without saving it (useful for helpline operators)."""
    return triage(body.text).to_dict()


@app.post("/api/requests", status_code=201)
def create_request(body: RequestIn):
    return create_or_merge(body)


_COORD_RE = re.compile(r"@\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)")


@app.post("/api/sms")
def sms_intake(body: SmsIn):
    """Webhook for an SMS gateway. Format: 'HELP <message> @<lat>,<lon>'.
    Returns the reply text the gateway should send back to the sender."""
    text = body.body.strip()
    m = _COORD_RE.search(text)
    if not m:
        return {"accepted": False,
                "reply": "ReliefLink: please resend with your location, e.g. HELP trapped on roof @13.04,80.25"}
    lat, lon = float(m.group(1)), float(m.group(2))
    message = re.sub(r"^\s*help\b[:\s]*", "", _COORD_RE.sub("", text), flags=re.I).strip() or "help needed"
    if len(message) < 3:
        message = "help needed"
    result = create_or_merge(RequestIn(text=message, lat=lat, lon=lon, contact=body.sender, source="sms"))
    req = result["request"]
    reply = (f"ReliefLink: request #{req['id']} received, priority {req['level']}. "
             "Stay where you are if safe. Help is being arranged.")
    if result["duplicate_of"]:
        reply = f"ReliefLink: this incident is already reported as #{req['id']}. Help is being arranged."
    return {"accepted": True, "reply": reply, "request_id": req["id"]}


@app.get("/api/requests")
def list_requests(status: str | None = None):
    with db.connect() as conn:
        if status:
            reqs = db.rows(conn, "SELECT * FROM requests WHERE status=?", (status,))
        else:
            reqs = db.rows(conn, "SELECT * FROM requests")
    reqs = [decorate(r) for r in reqs]
    return sorted(reqs, key=lambda r: (r["status"] == "resolved", -r["effective_urgency"]))


@app.get("/api/requests/{request_id}")
def get_request(request_id: int):
    with db.connect() as conn:
        req = db.row_to_dict(conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone())
        if not req:
            raise HTTPException(404, "Request not found")
        req["reports"] = db.rows(conn, "SELECT text, source, created_at FROM reports WHERE request_id=?", (request_id,))
    return decorate(req)


@app.post("/api/requests/{request_id}/resolve")
def resolve_request(request_id: int):
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone():
            raise HTTPException(404, "Request not found")
        now = db.now_iso()
        conn.execute("UPDATE requests SET status='resolved', updated_at=? WHERE id=?", (now, request_id))
        conn.execute("UPDATE assignments SET status='done' WHERE request_id=? AND status='active'", (request_id,))
    return {"resolved": request_id}


@app.post("/api/requests/{request_id}/review")
def review_request(request_id: int, category: str | None = None, urgency: int | None = None):
    """A coordinator confirms or corrects an AI triage decision."""
    if category is not None and category not in SKILL_FOR_NEED:
        raise HTTPException(400, f"category must be one of {sorted(SKILL_FOR_NEED)}")
    if urgency is not None and not 0 <= urgency <= 100:
        raise HTTPException(400, "urgency must be 0-100")
    with db.connect() as conn:
        req = db.row_to_dict(conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone())
        if not req:
            raise HTTPException(404, "Request not found")
        cat = category or req["category"]
        urg = req["urgency"] if urgency is None else urgency
        needs = [cat] + [n for n in req["needs"] if n != cat]
        reasons = req["reasons"] + [f"reviewed by coordinator ({cat}, {urg})"]
        conn.execute("UPDATE requests SET category=?, needs=?, urgency=?, level=?, reasons=?, needs_review=0, "
                     "updated_at=? WHERE id=?", (cat, json.dumps(needs), urg, level_for(urg),
                                                  json.dumps(reasons), db.now_iso(), request_id))
        return decorate(db.row_to_dict(conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()))


@app.post("/api/volunteers", status_code=201)
def add_volunteer(body: VolunteerIn):
    if not valid_coords(body.lat, body.lon):
        raise HTTPException(422, "invalid coordinates")
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO volunteers (name, phone, skills, lat, lon, capacity) VALUES (?,?,?,?,?,?)",
            (body.name, body.phone, json.dumps(body.skills), body.lat, body.lon, body.capacity),
        )
        return db.row_to_dict(conn.execute("SELECT * FROM volunteers WHERE id=?", (cur.lastrowid,)).fetchone())


@app.get("/api/volunteers")
def list_volunteers():
    with db.connect() as conn:
        return db.rows(conn, """
            SELECT v.*, COUNT(a.id) AS active_tasks
            FROM volunteers v LEFT JOIN assignments a ON a.volunteer_id = v.id AND a.status='active'
            GROUP BY v.id ORDER BY v.id""")


@app.get("/api/assignments")
def list_assignments():
    with db.connect() as conn:
        return db.rows(conn, """
            SELECT a.*, v.name AS volunteer_name, v.lat AS v_lat, v.lon AS v_lon,
                   r.lat AS r_lat, r.lon AS r_lon, r.category, r.level
            FROM assignments a
            JOIN volunteers v ON v.id = a.volunteer_id
            JOIN requests r ON r.id = a.request_id
            WHERE a.status = 'active' ORDER BY a.id""")


@app.post("/api/dispatch")
def dispatch(strategy: str = "optimal", dry_run: bool = False):
    """Assign free volunteers to open requests.
    strategy=optimal uses the Hungarian algorithm; strategy=greedy is the FCFS baseline."""
    if strategy not in ("optimal", "greedy"):
        raise HTTPException(400, "strategy must be 'optimal' or 'greedy'")
    with db.connect() as conn:
        volunteers, requests = load_dispatch_inputs(conn)
        plan = (optimal_dispatch if strategy == "optimal" else greedy_dispatch)(volunteers, requests)
        if not dry_run:
            now = db.now_iso()
            for a in plan:
                conn.execute(
                    "INSERT INTO assignments (volunteer_id, request_id, distance_km, eta_min, created_at) "
                    "VALUES (?,?,?,?,?)", (a.volunteer_id, a.request_id, a.distance_km, a.eta_min, now))
                conn.execute("UPDATE requests SET status='assigned', updated_at=? WHERE id=?", (now, a.request_id))
    return {"strategy": strategy, "dry_run": dry_run, "assigned": len(plan),
            "summary": summarize(plan, requests), "plan": [a.__dict__ for a in plan]}


@app.get("/api/dispatch/compare")
def compare_strategies():
    """Run both strategies on the current open requests without saving anything."""
    with db.connect() as conn:
        volunteers, requests = load_dispatch_inputs(conn)
    return {
        "optimal": summarize(optimal_dispatch(volunteers, requests), requests),
        "greedy": summarize(greedy_dispatch(volunteers, requests), requests),
    }


@app.get("/api/stats")
def stats():
    with db.connect() as conn:
        reqs = [decorate(r) for r in db.rows(conn, "SELECT * FROM requests")]
        reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        vols = conn.execute("SELECT COUNT(*) FROM volunteers WHERE active=1").fetchone()[0]
    open_reqs = [r for r in reqs if r["status"] == "open"]
    return {
        "open": len(open_reqs),
        "assigned": sum(r["status"] == "assigned" for r in reqs),
        "resolved": sum(r["status"] == "resolved" for r in reqs),
        "critical_open": sum(r["effective_level"] == "CRITICAL" for r in open_reqs),
        "needs_review": sum(bool(r["needs_review"]) for r in open_reqs),
        "people_waiting": sum(r["people"] for r in open_reqs),
        "reports_received": reports,
        "duplicates_merged": reports - len(reqs),
        "volunteers": vols,
    }


@app.post("/api/demo/seed")
def seed_demo():
    """Reset the database and load a realistic Chennai flood scenario."""
    from data.seed import REQUESTS, VOLUNTEERS
    with db.connect() as conn:
        db.reset(conn)
    for v in VOLUNTEERS:
        add_volunteer(VolunteerIn(**v))
    merged = 0
    for r in REQUESTS:
        if create_or_merge(RequestIn(**r))["duplicate_of"]:
            merged += 1
    return {"requests": len(REQUESTS), "duplicates_merged": merged, "volunteers": len(VOLUNTEERS)}

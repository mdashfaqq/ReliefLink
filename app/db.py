"""SQLite persistence. Lists are stored as JSON text columns."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT NOT NULL,
    lat          REAL NOT NULL,
    lon          REAL NOT NULL,
    contact      TEXT,
    source       TEXT NOT NULL DEFAULT 'web',
    language     TEXT,
    category     TEXT NOT NULL,
    needs        TEXT NOT NULL,
    urgency      INTEGER NOT NULL,
    level        TEXT NOT NULL,
    people       INTEGER NOT NULL DEFAULT 1,
    reasons      TEXT NOT NULL,
    report_count INTEGER NOT NULL DEFAULT 1,
    needs_review INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'open',   -- open | assigned | resolved
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (             -- every raw message, incl. duplicates
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS volunteers (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    phone     TEXT,
    skills    TEXT NOT NULL,
    lat       REAL NOT NULL,
    lon       REAL NOT NULL,
    capacity  INTEGER NOT NULL DEFAULT 1,
    active    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS assignments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    volunteer_id INTEGER NOT NULL REFERENCES volunteers(id) ON DELETE CASCADE,
    request_id   INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    distance_km  REAL NOT NULL,
    eta_min      INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',  -- active | done
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_assign_status ON assignments(status);
"""

JSON_COLUMNS = {"needs", "reasons", "skills"}


def db_path() -> str:
    return os.getenv("RELIEFLINK_DB", "relieflink.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in JSON_COLUMNS & d.keys():
        d[k] = json.loads(d[k])
    return d


def rows(conn, sql: str, params=()) -> list[dict]:
    return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def reset(conn):
    conn.executescript("DELETE FROM assignments; DELETE FROM reports; DELETE FROM requests; "
                       "DELETE FROM volunteers; DELETE FROM sqlite_sequence;")

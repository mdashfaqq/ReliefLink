"""Duplicate detection: many people report the same incident.

During a flood the same family on the same rooftop may be reported by the
family itself, two neighbours and a relative in another city. Treating these as
separate requests wastes rescue teams and buries other incidents.

Two reports are considered the same incident when they are:
  * close in space  (within DUP_RADIUS_KM), and
  * close in time   (within DUP_WINDOW_HOURS), and
  * about the same need (overlapping need categories), and
  * similar in text, OR almost exactly co-located.

Text similarity uses character n-gram TF-IDF, which works across scripts
(English, Hindi, Tamil) and tolerates typos without any model download.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .geo import haversine_km

DUP_RADIUS_KM = 0.5
NEAR_EXACT_KM = 0.08
DUP_WINDOW_HOURS = 12
TEXT_SIM_THRESHOLD = 0.30


def text_similarity(a: str, b: str) -> float:
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True)
    try:
        m = vec.fit_transform([a, b])
    except ValueError:  # empty vocabulary
        return 0.0
    return float(cosine_similarity(m[0], m[1])[0, 0])


def find_duplicate(new: dict, candidates: list[dict]) -> tuple[dict, float] | None:
    """Return (best matching open request, similarity) or None.

    `new` and each candidate need: text, lat, lon, needs (list), created_at (ISO str).
    """
    created = datetime.fromisoformat(new["created_at"])
    best, best_score = None, 0.0
    for c in candidates:
        if abs(created - datetime.fromisoformat(c["created_at"])) > timedelta(hours=DUP_WINDOW_HOURS):
            continue
        dist = haversine_km(new["lat"], new["lon"], c["lat"], c["lon"])
        if dist > DUP_RADIUS_KM:
            continue
        if not set(new["needs"]) & set(c["needs"]):
            continue
        sim = text_similarity(new["text"], c["text"])
        if sim < TEXT_SIM_THRESHOLD and dist > NEAR_EXACT_KM:
            continue
        # Prefer closer and more similar candidates.
        score = sim + (1 - dist / DUP_RADIUS_KM) * 0.5
        if score > best_score:
            best, best_score = c, score
    return (best, round(best_score, 3)) if best else None

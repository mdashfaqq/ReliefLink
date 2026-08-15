"""Volunteer dispatch as an optimal assignment problem.

Naive dispatch ("send the next free volunteer to the oldest request") ignores
three things that matter in a disaster:
  1. urgency   - a drowning risk should beat a blanket request
  2. skills    - a medical emergency needs a medic, a rooftop rescue needs a boat
  3. distance  - every minute of travel is a minute not spent helping

We build a cost matrix between volunteer *slots* (a volunteer with capacity 2
contributes two slots) and open requests, then solve it exactly with the
Hungarian algorithm (scipy.optimize.linear_sum_assignment), which minimises
total cost in O(n^3).

    cost(v, r) = - URGENCY_WEIGHT * urgency(r)  +  DISTANCE_WEIGHT * km(v, r)

Pairs that violate a hard constraint (missing skill, too far) get a prohibitive
cost and are dropped from the final plan.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from .geo import eta_minutes, haversine_km

# Which volunteer skill each need requires.
SKILL_FOR_NEED = {
    "rescue": "rescue",
    "medical": "medical",
    "water": "supplies",
    "food": "supplies",
    "shelter": "transport",
    "other": "general",
}

URGENCY_WEIGHT = 1.0
DISTANCE_WEIGHT = 4.0      # 1 km of travel costs as much as 4 urgency points
MAX_DISTANCE_KM = 15.0
INFEASIBLE = 1e6


@dataclass
class Assignment:
    volunteer_id: int
    request_id: int
    distance_km: float
    eta_min: int
    urgency: int


def can_serve(volunteer: dict, request: dict) -> bool:
    skills = set(volunteer["skills"])
    needed = SKILL_FOR_NEED.get(request["category"], "general")
    return needed in skills or needed == "general"


def build_cost_matrix(volunteers: list[dict], requests: list[dict]):
    slots = [v for v in volunteers for _ in range(max(0, int(v.get("capacity", 1))))]
    cost = np.full((len(slots), len(requests)), INFEASIBLE)
    dist = np.zeros_like(cost)
    for i, v in enumerate(slots):
        for j, r in enumerate(requests):
            d = haversine_km(v["lat"], v["lon"], r["lat"], r["lon"])
            dist[i, j] = d
            if d <= MAX_DISTANCE_KM and can_serve(v, r):
                cost[i, j] = -URGENCY_WEIGHT * r["urgency"] + DISTANCE_WEIGHT * d
    return slots, cost, dist


def optimal_dispatch(volunteers: list[dict], requests: list[dict]) -> list[Assignment]:
    if not volunteers or not requests:
        return []
    slots, cost, dist = build_cost_matrix(volunteers, requests)
    if not slots:
        return []
    rows, cols = linear_sum_assignment(cost)
    plan = []
    for i, j in zip(rows, cols):
        if cost[i, j] >= INFEASIBLE:
            continue
        d = float(dist[i, j])
        plan.append(Assignment(slots[i]["id"], requests[j]["id"], round(d, 2), eta_minutes(d), requests[j]["urgency"]))
    return sorted(plan, key=lambda a: -a.urgency)


def greedy_dispatch(volunteers: list[dict], requests: list[dict]) -> list[Assignment]:
    """Baseline: first-come-first-served. Each request, oldest first, gets the
    nearest free volunteer who has the right skill."""
    remaining = {v["id"]: int(v.get("capacity", 1)) for v in volunteers}
    by_id = {v["id"]: v for v in volunteers}
    plan = []
    for r in sorted(requests, key=lambda r: r["created_at"]):
        options = []
        for vid, cap in remaining.items():
            v = by_id[vid]
            if cap <= 0 or not can_serve(v, r):
                continue
            d = haversine_km(v["lat"], v["lon"], r["lat"], r["lon"])
            if d <= MAX_DISTANCE_KM:
                options.append((d, vid))
        if options:
            d, vid = min(options)
            remaining[vid] -= 1
            plan.append(Assignment(vid, r["id"], round(d, 2), eta_minutes(d), r["urgency"]))
    return plan


def summarize(plan: list[Assignment], requests: list[dict]) -> dict:
    """Metrics used to compare dispatch strategies."""
    critical_ids = {r["id"] for r in requests if r["urgency"] >= 70}
    served = {a.request_id for a in plan}
    return {
        "requests_served": len(served),
        "critical_total": len(critical_ids),
        "critical_served": len(critical_ids & served),
        "urgency_served": sum(a.urgency for a in plan),
        "total_km": round(sum(a.distance_km for a in plan), 1),
        "avg_eta_min": round(sum(a.eta_min for a in plan) / len(plan), 1) if plan else 0,
    }

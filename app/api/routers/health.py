"""Round 2 poller-health introspection endpoint.

  GET /api/health/poller  -- global + per-leader poller summary

Reads from PollerManager state via AppState. No auth handled here; the
global Bearer middleware in main.py covers /api/* including this path.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List

from fastapi import APIRouter

from ...core.time import now_ms

router = APIRouter()


def _get_state():
    from ..main import state  # noqa: WPS433
    return state


def _percentile(samples: List[float], pct: float) -> float:
    """Compute pct-percentile (0-100) without numpy.

    Uses linear interpolation between closest ranks. Returns 0.0 on an
    empty sample list to keep the JSON response well-typed.
    """
    if not samples:
        return 0.0
    if len(samples) == 1:
        return float(samples[0])
    sorted_samples = sorted(samples)
    k = (len(sorted_samples) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_samples) - 1)
    if f == c:
        return float(sorted_samples[f])
    d0 = sorted_samples[f] * (c - k)
    d1 = sorted_samples[c] * (k - f)
    return float(d0 + d1)


@router.get("/health/poller")
async def poller_health() -> Dict[str, Any]:
    state = _get_state()
    now = now_ms()

    # running() returns {project_key: bool}; "running" if at least one project
    # has a live polling task. We keep the boolean coarse on purpose.
    running_map = state.poller.running()
    poller_running = any(running_map.values())

    leaders_total = 0
    leaders_live = 0
    leaders_stale = 0
    leaders_offline = 0
    auth_error_count = 0
    all_latencies: List[float] = []
    per_leader: List[Dict[str, Any]] = []

    for leader in state.list_leaders():
        leaders_total += 1
        leader_id = leader.leader_id
        project, pstate = state.project_state_for_leader(leader_id, None)
        last_poll_at = pstate.last_fetch_at if pstate else 0
        age = now - last_poll_at if last_poll_at else 10**9
        auth_err = bool(pstate.last_fetch_auth_error) if pstate else False
        latencies = list(pstate.poll_latencies) if pstate else []
        all_latencies.extend(latencies)

        if auth_err:
            auth_error_count += 1
            leaders_offline += 1
        elif age < 8000:
            leaders_live += 1
        elif age < 30000:
            leaders_stale += 1
        else:
            leaders_offline += 1

        per_leader.append(
            {
                "leader_id": leader_id,
                "last_poll_age_ms": age if last_poll_at else 0,
                "avg_latency_ms": round(statistics.fmean(latencies), 2) if latencies else 0.0,
                "error": (pstate.last_fetch_error if pstate else "") or "",
            }
        )

    return {
        "poller_running": poller_running,
        "leaders_total": leaders_total,
        "leaders_live": leaders_live,
        "leaders_stale": leaders_stale,
        "leaders_offline": leaders_offline,
        "global_avg_poll_latency_ms": round(statistics.fmean(all_latencies), 2)
        if all_latencies
        else 0.0,
        "global_p95_poll_latency_ms": round(_percentile(all_latencies, 95.0), 2),
        "auth_error_count": auth_error_count,
        "per_leader": per_leader,
    }

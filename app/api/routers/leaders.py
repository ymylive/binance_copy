"""Round 2 signal-centric leader endpoints.

Mounted under /api by app.api.main. Three endpoints live here:

  GET /api/leaders                      -- rich list (overrides legacy stub)
  GET /api/leaders/{leader_id}/sync     -- leader-vs-mirror diff
  GET /api/leaders/{leader_id}/cadence  -- open/add/reduce/close histogram

The legacy /api/leaders endpoint registered directly on app returns just the
raw LeaderConfig list. By including this router BEFORE that endpoint runs we
shadow it for callers that want the enriched payload while leaving the path
free of breaking renames. Bearer-token auth is applied by the global
middleware in main.py for every /api/* path so we do not re-check here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from ...core.time import now_ms

router = APIRouter()


def _get_state():
    """Late import to avoid circular dependency with app.api.main."""
    from ..main import state  # noqa: WPS433 - intentional lazy import
    return state


def _resolve_leader_state_label(last_poll_age_ms: int, auth_error: bool) -> str:
    """Map poller fetch age + auth flag to a coarse health label.

    Thresholds match the spec:
      - age <  8000 ms        -> live
      - age < 30000 ms        -> stale
      - age >= 30000 ms       -> offline
      - any auth error        -> auth_error (overrides above)
    """
    if auth_error:
        return "auth_error"
    if last_poll_age_ms < 8000:
        return "live"
    if last_poll_age_ms < 30000:
        return "stale"
    return "offline"


def _aggregate_signals_24h(events, leader_id: str, now: int) -> Dict[str, int]:
    """Count signals in the last 24h bucketed by mirror_status."""
    cutoff = now - 86_400_000
    buckets = {"sent": 0, "skipped": 0, "failed": 0, "pending": 0}
    total = 0
    for evt in events:
        if (evt.leader_id or evt.portfolio_id) != leader_id:
            continue
        if evt.created_at < cutoff:
            continue
        total += 1
        status = evt.mirror_status if evt.mirror_status in buckets else "pending"
        buckets[status] = buckets.get(status, 0) + 1
    buckets["total"] = total
    return buckets


@router.get("/leaders")
async def list_leaders_enriched() -> List[Dict[str, Any]]:
    """Aggregate LeaderConfig + project state + live metrics per leader."""
    state = _get_state()
    now = now_ms()
    rows: List[Dict[str, Any]] = []

    for leader in state.list_leaders():
        leader_id = leader.leader_id
        # Locate the driving project so we can read poller-level metrics.
        project, pstate = state.project_state_for_leader(leader_id, None)
        account_id = (
            project.trade_account_id if project and project.trade_account_id else "default"
        )

        last_poll_at = pstate.last_fetch_at if pstate else 0
        last_poll_age = now - last_poll_at if last_poll_at else 10**9
        auth_error = bool(pstate.last_fetch_auth_error) if pstate else False
        latencies = list(pstate.poll_latencies) if pstate else []
        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        positions_count = (
            sum(1 for _ in pstate.leader_current_positions) if pstate else 0
        )
        leader_equity = (
            (pstate.leader_margin or pstate.leader_aum or 0.0) if pstate else 0.0
        )
        follower_equity = pstate.follower_equity if pstate else 0.0
        last_error = pstate.last_fetch_error if pstate else ""

        signals_buckets = _aggregate_signals_24h(state.events, leader_id, now)
        denom = (
            signals_buckets["sent"]
            + signals_buckets["failed"]
            + signals_buckets["skipped"]
        )
        accuracy = (signals_buckets["sent"] / denom * 100.0) if denom else 100.0

        # compute_leader_sync is async; we cache 3s so a hot list call is fine.
        sync_summary = await state.compute_leader_sync(leader_id, account_id)
        deviation_summary = sync_summary.get("summary", {})
        deviation_pct = round(100.0 - float(deviation_summary.get("accuracy_pct", 100.0)), 4)

        rows.append(
            {
                "leader_id": leader_id,
                "account_id": account_id,
                "exchange": leader.exchange,
                "source": leader.source,
                "name": leader.name,
                "enabled": leader.enabled,
                "state": _resolve_leader_state_label(last_poll_age, auth_error),
                "last_poll_at_ms": last_poll_at,
                "last_poll_age_ms": last_poll_age if last_poll_at else 0,
                "avg_poll_latency_ms": avg_latency,
                "current_positions_count": positions_count,
                "leader_equity": leader_equity,
                "follower_equity": follower_equity,
                "signals_24h": signals_buckets["total"],
                "mirror_accuracy_pct": round(accuracy, 2),
                "deviation_pct": deviation_pct,
                "last_error": last_error or "",
            }
        )
    return rows


@router.get("/leaders/{leader_id}/sync")
async def leader_sync(
    leader_id: str,
    account_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Leader-vs-mirror per-symbol diff, cached 3s in state."""
    state = _get_state()
    return await state.compute_leader_sync(leader_id, account_id)


@router.get("/leaders/{leader_id}/cadence")
async def leader_cadence(
    leader_id: str,
    bucket_ms: int = Query(default=300_000, ge=1_000),
    hours: int = Query(default=24, ge=1, le=168),
) -> Dict[str, Any]:
    """Bucketed open/add/reduce/close counts over a rolling time window."""
    state = _get_state()
    now = now_ms()
    window_ms = hours * 3_600_000
    cutoff = now - window_ms

    # Pre-allocate buckets so the response is dense (front-end charts expect
    # gaps to appear as zeros, not missing keys).
    bucket_count = max(1, window_ms // bucket_ms)
    start_bucket = (cutoff // bucket_ms) * bucket_ms
    buckets: Dict[int, Dict[str, int]] = {
        start_bucket + i * bucket_ms: {"open": 0, "add": 0, "reduce": 0, "close": 0}
        for i in range(bucket_count)
    }

    for evt in state.events:
        if (evt.leader_id or evt.portfolio_id) != leader_id:
            continue
        if evt.created_at < cutoff:
            continue
        action = evt.action
        if action not in {"open", "add", "reduce", "close"}:
            continue
        bucket_ts = (evt.created_at // bucket_ms) * bucket_ms
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {"open": 0, "add": 0, "reduce": 0, "close": 0}
        buckets[bucket_ts][action] += 1

    rendered = [
        {"ts_ms": ts, **counts}
        for ts, counts in sorted(buckets.items())
    ]
    return {
        "leader_id": leader_id,
        "bucket_ms": bucket_ms,
        "hours": hours,
        "buckets": rendered,
    }

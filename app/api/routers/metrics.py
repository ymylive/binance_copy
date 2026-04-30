"""Round 2 aggregate metrics endpoints.

  GET /api/metrics/mirror-accuracy  -- global accuracy time series

Bucketed mirror accuracy across the rolling event deque. Useful for the new
console dashboard's "executor health" sparkline.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Query

from ...core.time import now_ms

router = APIRouter()


def _get_state():
    from ..main import state  # noqa: WPS433
    return state


@router.get("/metrics/mirror-accuracy")
async def mirror_accuracy(
    bucket_ms: int = Query(default=300_000, ge=1_000),
    hours: int = Query(default=6, ge=1, le=72),
) -> Dict[str, Any]:
    """Bucketed sent / (sent+failed+skipped) ratio over a rolling window."""
    state = _get_state()
    now = now_ms()
    window_ms = hours * 3_600_000
    cutoff = now - window_ms

    bucket_count = max(1, window_ms // bucket_ms)
    start_bucket = (cutoff // bucket_ms) * bucket_ms
    # Keep two counters per bucket so the ratio is computable at render time
    # without a second pass. "denominator" excludes "pending" (still in flight).
    buckets: Dict[int, Dict[str, int]] = {
        start_bucket + i * bucket_ms: {"sent": 0, "failed": 0, "skipped": 0, "total": 0}
        for i in range(bucket_count)
    }

    for evt in state.events:
        if evt.created_at < cutoff:
            continue
        ts = (evt.created_at // bucket_ms) * bucket_ms
        if ts not in buckets:
            buckets[ts] = {"sent": 0, "failed": 0, "skipped": 0, "total": 0}
        bucket = buckets[ts]
        bucket["total"] += 1
        status = evt.mirror_status
        if status in {"sent", "failed", "skipped"}:
            bucket[status] += 1

    rendered: List[Dict[str, Any]] = []
    for ts in sorted(buckets.keys()):
        b = buckets[ts]
        denom = b["sent"] + b["failed"] + b["skipped"]
        accuracy = (b["sent"] / denom * 100.0) if denom else 100.0
        rendered.append(
            {
                "ts_ms": ts,
                "accuracy_pct": round(accuracy, 2),
                "signals": b["total"],
                "failures": b["failed"],
            }
        )
    return {"buckets": rendered}

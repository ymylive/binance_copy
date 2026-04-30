"""Round 2 signal-centric endpoints.

  GET /api/signals             -- lifecycle-aware signal history (replaces /events for new UI)
  GET /api/signals/stream      -- Server-Sent Events fan-out

The SSE endpoint cannot use Authorization headers because the browser's
EventSource API does not let callers attach custom headers. We therefore
accept the same API token via a ?token= query parameter on this single path.
The check uses secrets.compare_digest to defeat timing attacks. The global
Bearer middleware (in app.api.main) is configured to skip this path so the
token check runs here exclusively.
"""
from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ...core.time import now_ms

router = APIRouter()

# Keepalive interval matches typical reverse-proxy idle timeouts (60s on
# nginx, 30s on most cloud LBs). 30s is a safe lower bound.
SSE_KEEPALIVE_INTERVAL_S = 30.0


def _get_state():
    from ..main import state  # noqa: WPS433
    return state


def _get_api_token() -> str:
    from ..main import API_TOKEN  # noqa: WPS433
    return API_TOKEN


@router.get("/signals")
async def list_signals(
    leader_id: Optional[str] = Query(default=None),
    since_ms: Optional[int] = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    """Return recent signals from the in-memory deque, newest first."""
    state = _get_state()
    out: List[Dict[str, Any]] = []
    for evt in state.events:
        if leader_id and (evt.leader_id or evt.portfolio_id) != leader_id:
            continue
        if since_ms is not None and evt.created_at < since_ms:
            continue
        out.append(state.serialize_signal(evt))
        if len(out) >= limit:
            break
    return out


@router.get("/signals/stream")
async def signals_stream(
    request: Request,
    token: str = Query(default=""),
) -> StreamingResponse:
    """Server-Sent Events stream of new signals.

    Auth model: ?token=... only. The Bearer middleware in main.py whitelists
    this path so callers MUST present the token here. Token comparison uses
    secrets.compare_digest to defeat timing attacks.
    """
    expected = _get_api_token()
    if not expected:
        raise HTTPException(status_code=503, detail="api token not configured")
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="unauthorized")

    state = _get_state()
    queue = state.subscribe_signals()

    async def event_generator() -> AsyncGenerator[bytes, None]:
        # Initial comment so the connection is "open" from the client's POV
        # without sending a phantom signal.
        yield b": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=SSE_KEEPALIVE_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    # Idle keepalive prevents proxies from killing the stream.
                    yield b": ping\n\n"
                    continue
                payload = state.serialize_signal(event)
                data = json.dumps(payload, default=str)
                yield f"event: signal\ndata: {data}\n\n".encode("utf-8")
        except asyncio.CancelledError:
            # Normal disconnect; let the finally block clean up.
            raise
        finally:
            state.unsubscribe_signals(queue)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",  # disable nginx buffering
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )

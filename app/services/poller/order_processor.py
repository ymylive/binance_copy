from __future__ import annotations

import math
import uuid
from typing import Any, Dict, Optional, Set, Tuple

from .state_manager import ProjectState
from .data_utils import DataUtils
from ...core.logging import get_logger
from ...core.time import now_ms
from ...domain.config import ProjectConfig
from ...domain.events import OrderEvent

logger = get_logger()


class OrderProcessor:
    """Processes order history and handles position reconciliation"""

    def __init__(self, executor, event_sink):
        self._executor = executor
        self._event_sink = event_sink

    def seed_positions_from_snapshot(self, state: ProjectState) -> None:
        """Initialize positions from snapshot data"""
        for item in state.positions_snapshot:
            status = self._history_status(item)
            if status is not True:
                continue
            symbol = str(item.get("symbol") or "")
            if not symbol:
                continue
            position_side = self._normalize_history_side(item.get("side"))
            if not position_side:
                continue
            qty = item.get("position_qty")
            if qty is None:
                continue
            try:
                qty_value = float(qty)
            except (TypeError, ValueError):
                continue
            if math.isclose(qty_value, 0.0):
                continue
            key = DataUtils.position_key(symbol, position_side)
            if position_side.upper() == "BOTH":
                state.positions[key] = qty_value
            else:
                state.positions[key] = abs(qty_value)

    def infer_reduce_only(
        self,
        item: Dict[str, Any],
        state: ProjectState,
        symbol: str,
        position_side: str,
        side: str,
    ) -> bool:
        """Infer if order is reduce-only"""
        reduce_only = DataUtils.is_reduce_only(item, position_side, side)
        if reduce_only:
            return True
        open_sides = self._leader_open_sides(state, symbol)
        if len(open_sides) != 1:
            return False
        only = next(iter(open_sides))
        side = side.upper()
        if only == "LONG" and side == "SELL":
            return True
        if only == "SHORT" and side == "BUY":
            return True
        return False

    def infer_position_side(
        self,
        state: ProjectState,
        symbol: str,
        position_side: str,
        side: str,
        reduce_only: bool,
    ) -> str:
        """Infer position side from order data"""
        raw = (position_side or "").upper()
        if raw and raw != "BOTH":
            return raw
        open_sides = self._leader_open_sides(state, symbol)
        if len(open_sides) == 1:
            return next(iter(open_sides))
        side = side.upper()
        inferred = ""
        if reduce_only:
            if side == "SELL":
                inferred = "LONG"
            elif side == "BUY":
                inferred = "SHORT"
        else:
            if side == "BUY":
                inferred = "LONG"
            elif side == "SELL":
                inferred = "SHORT"
        if inferred and (not open_sides or inferred in open_sides):
            return inferred
        return raw or "BOTH"

    async def reconcile_full_closes(
        self,
        project: ProjectConfig,
        state: ProjectState,
    ) -> None:
        """Reconcile fully closed positions from history"""
        if not state.positions_snapshot:
            return
        latest: Dict[str, Tuple[int, Dict[str, object], str, str]] = {}
        for item in state.positions_snapshot:
            symbol = str(item.get("symbol") or "")
            if not symbol:
                continue
            position_side = self._normalize_history_side(item.get("side"))
            if not position_side:
                continue
            key = DataUtils.position_key(symbol, position_side)
            recency = self._position_recency(item)
            prev = latest.get(key)
            if not prev or recency >= prev[0]:
                latest[key] = (recency, item, symbol, position_side)

        for key, (recency, item, symbol, position_side) in latest.items():
            status = self._history_status(item)
            if status is not False:
                continue
            marker = self._position_recency(item)
            if marker <= 0:
                marker = recency or now_ms()
            last_marker = state.closed_positions_seen.get(key, 0)
            if last_marker and marker <= last_marker:
                continue
            leader_amt = state.positions.get(key, 0.0)
            if not leader_amt or math.isclose(leader_amt, 0.0):
                state.closed_positions_seen[key] = marker
                state.positions[key] = 0.0
                state.follower_positions[key] = 0.0
                continue
            side = "SELL" if position_side.upper() == "LONG" else "BUY"
            follower_before = state.follower_positions.get(key, 0.0)
            fallback_qty = abs(follower_before) if abs(follower_before) > 0 else abs(
                leader_amt
            )
            if fallback_qty <= 0:
                state.closed_positions_seen[key] = marker
                continue
            follower_qty = -fallback_qty if side == "SELL" else fallback_qty
            now = now_ms()
            event = OrderEvent(
                event_id=str(uuid.uuid4()),
                portfolio_id=project.portfolio_id,
                exchange=project.exchange,
                trade_account_id=project.trade_account_id or None,
                order_id="",
                trade_id="",
                action="close",
                symbol=symbol,
                position_side=position_side,
                side=side,
                executed_qty=abs(leader_amt),
                avg_price=0.0,
                order_time=marker,
                order_update_time=marker,
                leader_delta=-abs(leader_amt),
                scale=0.0,
                follower_qty=follower_qty,
                reduce_only=True,
                order_value=0.0,
                follower_notional=None,
                leader_open_pct=None,
                leader_close_pct=1.0,
                follower_leverage=project.follower_leverage,
                status="queued",
                note="history_close_reconcile",
                created_at=now,
            )
            self._event_sink(event)
            if event.status == "queued":
                await self._executor.execute(event)
            state.positions[key] = 0.0
            state.follower_positions[key] = 0.0
            state.closed_positions_seen[key] = marker

    def _leader_open_sides(self, state: ProjectState, symbol: str) -> Set[str]:
        """Get open position sides for a symbol"""
        sides = set()
        for key, qty in state.positions.items():
            if not key.startswith(symbol.upper() + "|"):
                continue
            if abs(qty) > 1e-8:
                parts = key.split("|")
                if len(parts) >= 2:
                    sides.add(parts[1])
        return sides

    def _history_status(self, item: Dict[str, object]) -> Optional[bool]:
        """Get position status from history item"""
        status = item.get("status")
        if status == "ACTIVE":
            return True
        if status == "CLOSED":
            return False
        return None

    def _normalize_history_side(self, side: object) -> str:
        """Normalize position side from history"""
        if not side:
            return ""
        s = str(side).upper()
        if s in {"LONG", "SHORT", "BOTH"}:
            return s
        return ""

    def _position_recency(self, item: Dict[str, Any]) -> int:
        """Get recency timestamp from position item"""
        return DataUtils.get_ts(item, ("update_time", "time", "timestamp"))

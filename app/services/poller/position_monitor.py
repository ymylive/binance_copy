from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from .state_manager import ProjectState
from .data_utils import DataUtils
from ...core.logging import get_logger
from ...domain.config import ProjectConfig
from ...domain.events import OrderEvent

logger = get_logger()

# Constants
POSITION_CONFIRM_HITS = 2
POSITION_MISSING_CLOSE_HITS = 3


class PositionMonitor:
    """Monitors and tracks position changes for copy trading"""

    def __init__(self, leader_session, event_sink):
        self._leader = leader_session
        self._event_sink = event_sink

    async def run_position_monitor(
        self,
        project: ProjectConfig,
        state: ProjectState,
        leader_now_ms: int,
        leader_session=None,
        leader_equity: float = 0.0,
    ) -> None:
        """Main position monitoring loop"""
        raw_positions: List[Dict[str, Any]] = []
        ok = False
        error = ""
        auth_error = False
        require_side = False
        session = leader_session or self._leader

        leader_id = project.portfolio_id
        if project.exchange == "okx" and project.leader_id:
            leader_id = project.leader_id

        # Fetch positions with retry
        max_retries = 2
        payload = None
        for attempt in range(max_retries + 1):
            logger.info(
                "[FETCH] Starting fetch for portfolio %s (attempt %d/%d)",
                leader_id,
                attempt + 1,
                max_retries + 1,
            )
            # Round 2: measure fetch_positions() latency and feed a rolling
            # window on the project state for ops dashboards.
            t0 = time.perf_counter()
            try:
                payload = await session.fetch_positions(leader_id)
            finally:
                dur_ms = (time.perf_counter() - t0) * 1000.0
                try:
                    state.poll_latencies.append(dur_ms)
                except Exception:
                    # Defensive: never let metric collection break the poller.
                    pass

            if payload.get("success"):
                logger.info(
                    "[FETCH] Success: positions=%d, position_show=%s, empty_confirmed=%s",
                    len(payload.get("positions") or []),
                    payload.get("position_show"),
                    payload.get("empty_confirmed"),
                )
                break

            logger.warning(
                "[FETCH] Failed (attempt %d/%d): error=%s",
                attempt + 1,
                max_retries + 1,
                payload.get("error"),
            )

            if attempt < max_retries:
                await asyncio.sleep(1)

        ok = bool(payload.get("success"))
        error = str(payload.get("error") or "")
        auth_error = self._is_auth_error(error)

        # Extract positions from API response (data is array)
        if ok:
            raw_positions = DataUtils.extract_positions_data(payload)
        else:
            raw_positions = []
        require_side = ok
        empty_confirmed = bool(payload.get("empty_confirmed", False))
        payload_show = payload.get("position_show")

        # Note: API returns positions array directly in data, no totalMargin field
        # Leader margin would need to be calculated from positions if needed

        # Update position_show state
        if isinstance(payload_show, bool):
            state.position_show = payload_show
        elif isinstance(payload_show, (int, float)):
            state.position_show = bool(payload_show)
        elif isinstance(payload_show, str):
            value = payload_show.strip().lower()
            if value in {"true", "1", "yes"}:
                state.position_show = True
            elif value in {"false", "0", "no"}:
                state.position_show = False

        if ok and raw_positions:
            error = ""
            auth_error = False
            state.position_show = True

        if error == "login_required" and self._has_auth_hint():
            error = "position_unavailable"
            auth_error = False

        # Handle position hidden
        if state.position_show is False:
            error_msg = error or "position_hidden"
            self._update_fetch_status(state, False, error_msg, auth_error)
            if not state.position_hidden_notified:
                state.position_hidden_notified = True
                event = OrderEvent(
                    event_id=str(uuid.uuid4()),
                    portfolio_id=project.portfolio_id,
                    exchange=project.exchange,
                    trade_account_id=project.trade_account_id or None,
                    order_id="",
                    trade_id="",
                    action="error",
                    symbol="",
                    position_side="",
                    side="",
                    executed_qty=0.0,
                    avg_price=0.0,
                    order_time=0,
                    order_update_time=0,
                    leader_delta=0.0,
                    scale=0.0,
                    follower_qty=0.0,
                    reduce_only=False,
                    order_value=0.0,
                    follower_leverage=project.follower_leverage,
                    status="error",
                    note="position hidden; join copy-trade first",
                    created_at=leader_now_ms,
                )
                self._event_sink(event)
            return

        self._update_fetch_status(state, ok, error, auth_error)
        if not ok:
            return

        state.position_hidden_notified = False

        # Normalize positions
        positions_data: List[Dict[str, Any]] = []
        for pos in raw_positions:
            if not isinstance(pos, dict):
                continue
            normalized = self._normalize_position_item(
                pos, project.leader_leverage, require_side=require_side
            )
            if normalized:
                positions_data.append(normalized)

        # Build new positions map
        new_positions: Dict[str, Dict[str, Any]] = {}
        for pos in positions_data:
            if not isinstance(pos, dict):
                continue
            symbol = str(pos.get("symbol") or "")
            position_side = str(pos.get("positionSide") or "BOTH").upper()
            if not symbol:
                continue
            key = DataUtils.position_key(symbol, position_side)
            new_positions[key] = pos

        # Confirm positions with hit tracking
        confirmed_positions: Dict[str, Dict[str, Any]] = {}

        for key, pos in new_positions.items():
            signature = DataUtils.position_signature(pos)
            previous = state.position_signature.get(key)
            if previous == signature:
                hits = state.position_signature_hits.get(key, 0) + 1
            else:
                hits = 1
                state.position_signature[key] = signature
            state.position_signature_hits[key] = hits
            state.position_missing_hits[key] = 0
            if hits >= POSITION_CONFIRM_HITS:
                confirmed_positions[key] = pos
            elif key in state.leader_current_positions:
                confirmed_positions[key] = state.leader_current_positions[key]

        # Handle missing positions
        for key in list(state.leader_current_positions.keys()):
            if key in new_positions:
                continue
            miss_hits = state.position_missing_hits.get(key, 0) + 1
            state.position_missing_hits[key] = miss_hits
            if miss_hits < POSITION_CONFIRM_HITS or not empty_confirmed:
                confirmed_positions[key] = state.leader_current_positions[key]
            else:
                state.position_signature.pop(key, None)
                state.position_signature_hits.pop(key, None)
                state.position_missing_hits.pop(key, None)

        # Track empty positions
        if not new_positions and state.leader_current_positions:
            state.empty_positions_hits += 1
            if state.empty_positions_hits < POSITION_CONFIRM_HITS:
                return
        else:
            state.empty_positions_hits = 0

        # Initialize copy: if first time seeing positions and they are in loss, copy them immediately
        if not state.initial_positions_copied and confirmed_positions and not state.leader_current_positions:
            for key, pos in confirmed_positions.items():
                unrealized_profit = DataUtils.safe_float(pos.get("unrealizedProfit"))
                if unrealized_profit < 0:
                    symbol = str(pos.get("symbol") or "")
                    position_amt = self._signed_position_amount(pos)
                    entry_price = DataUtils.safe_float(pos.get("entryPrice"))

                    if symbol and position_amt != 0:
                        from .event_generator import EventGenerator
                        from .risk_calculator import RiskCalculator

                        leader_equity_value, follower_equity = self._resolve_equities(
                            project, state, leader_equity
                        )
                        follower_qty, follower_notional = RiskCalculator().calc_margin_ratio_qty(
                            abs(position_amt),
                            entry_price,
                            leader_equity_value,
                            follower_equity,
                            project.scale_value,
                        )

                        if follower_qty and follower_qty > 0:
                            event = EventGenerator().create_position_event(
                                project=project,
                                symbol=symbol,
                                position_side=str(pos.get("positionSide") or "BOTH").upper(),
                                side="BUY" if position_amt > 0 else "SELL",
                                executed_qty=abs(position_amt),
                                avg_price=entry_price,
                                follower_qty=follower_qty,
                                follower_notional=follower_notional,
                                action="open",
                                reduce_only=False,
                                leader_now=leader_now_ms,
                                note=f"Init copy loss {unrealized_profit:.2f}",
                            )
                            self._event_sink(event)
            state.initial_positions_copied = True

        # Detect position changes and generate add/reduce events
        self._detect_position_changes(
            project=project,
            state=state,
            old_positions=state.leader_current_positions,
            new_positions=confirmed_positions,
            leader_now_ms=leader_now_ms,
            leader_equity=leader_equity,
        )

        # Update state
        state.leader_current_positions = confirmed_positions

        # Update snapshot for frontend
        snapshot_items: List[Dict[str, object]] = []
        for pos in positions_data:
            if not isinstance(pos, dict):
                continue
            symbol = str(pos.get("symbol") or "")
            if not symbol:
                continue
            position_side = str(pos.get("positionSide") or "BOTH").upper()
            position_amt = self._signed_position_amount(pos)
            entry_price = DataUtils.safe_float(pos.get("entryPrice"))
            mark_price = DataUtils.safe_float(pos.get("markPrice"))
            unrealized_profit = DataUtils.safe_float(pos.get("unrealizedProfit"))
            side = (
                "LONG"
                if position_amt > 0
                else "SHORT" if position_amt < 0 else position_side
            )
            snapshot_items.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "status": "ACTIVE" if position_amt != 0 else "CLOSED",
                    "position_amt": abs(position_amt),
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "unrealized_profit": unrealized_profit,
                }
            )
        state.positions_snapshot = snapshot_items

    def _normalize_position_item(
        self, pos: Dict[str, Any], leader_leverage: int, require_side: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Normalize position item from API response"""
        # Filter out positions with zero amount
        position_amt = DataUtils.safe_float(pos.get("positionAmount"))
        if position_amt == 0:
            return None
        return pos

    def _is_auth_error(self, error: str) -> bool:
        """Check if error is authentication related"""
        return "login" in error.lower() or "auth" in error.lower()

    def _has_auth_hint(self) -> bool:
        """Check if there's an authentication hint"""
        return False

    def _update_fetch_status(
        self, state: ProjectState, ok: bool, error: str, auth_error: bool
    ) -> None:
        """Update fetch status in state"""
        state.last_fetch_ok = ok
        state.last_fetch_error = error
        state.last_fetch_auth_error = auth_error

    def _detect_position_changes(
        self,
        project: ProjectConfig,
        state: ProjectState,
        old_positions: Dict[str, Dict[str, Any]],
        new_positions: Dict[str, Dict[str, Any]],
        leader_now_ms: int,
        leader_equity: float = 0.0,
    ) -> None:
        """Detect position size changes and generate add/reduce events"""
        from .event_generator import EventGenerator
        from .risk_calculator import RiskCalculator

        for key, new_pos in new_positions.items():
            old_pos = old_positions.get(key)
            if not old_pos:
                continue

            symbol = str(new_pos.get("symbol") or "")
            position_side = str(new_pos.get("positionSide") or "BOTH").upper()

            old_amt = self._signed_position_amount(old_pos)
            new_amt = self._signed_position_amount(new_pos)

            if abs(old_amt) == 0 or abs(new_amt) == 0:
                continue

            delta = abs(new_amt) - abs(old_amt)

            if abs(delta) < 1e-8:
                continue

            entry_price = DataUtils.safe_float(new_pos.get("entryPrice"))

            if delta > 0:
                action = "add"
                side = "BUY" if new_amt > 0 else "SELL"
                reduce_only = False
            else:
                action = "reduce"
                side = "SELL" if new_amt > 0 else "BUY"
                reduce_only = True

            leader_equity_value, follower_equity = self._resolve_equities(
                project, state, leader_equity
            )
            follower_qty, follower_notional = RiskCalculator().calc_margin_ratio_qty(
                abs(delta),
                entry_price,
                leader_equity_value,
                follower_equity,
                project.scale_value,
            )

            if follower_qty and follower_qty > 0:
                event = EventGenerator().create_position_event(
                    project=project,
                    symbol=symbol,
                    position_side=position_side,
                    side=side,
                    executed_qty=abs(delta),
                    avg_price=entry_price,
                    follower_qty=follower_qty,
                    follower_notional=follower_notional,
                    action=action,
                    reduce_only=reduce_only,
                    leader_now=leader_now_ms,
                    leader_delta=delta,
                    note=f"Position {action}",
                )
                self._event_sink(event)

    def _signed_position_amount(self, pos: Dict[str, Any]) -> float:
        amt = DataUtils.safe_float(pos.get("positionAmt"))
        if amt != 0:
            return amt
        amt = DataUtils.safe_float(pos.get("positionAmount"))
        if amt == 0:
            return 0.0
        side = str(pos.get("positionSide") or "").upper()
        if side == "SHORT":
            return -abs(amt)
        if side == "LONG":
            return abs(amt)
        return amt

    def _resolve_equities(
        self,
        project: ProjectConfig,
        state: ProjectState,
        leader_equity: float,
    ) -> tuple[float, float]:
        if leader_equity <= 0:
            if state.leader_margin > 0:
                leader_equity = state.leader_margin
            elif state.leader_aum > 0:
                leader_equity = state.leader_aum
        follower_equity = state.follower_equity if state.follower_equity > 0 else project.follower_equity
        return leader_equity, follower_equity

from __future__ import annotations

import uuid
from typing import Optional

from ...domain.config import ProjectConfig
from ...domain.events import OrderEvent


class EventGenerator:
    """Generates order events for copy trading actions"""

    def create_position_event(
        self,
        project: ProjectConfig,
        symbol: str,
        position_side: str,
        side: str,
        executed_qty: float,
        avg_price: float,
        follower_qty: float,
        follower_notional: Optional[float],
        action: str,
        reduce_only: bool,
        leader_now: int,
        leader_delta: Optional[float] = None,
        leader_open_pct: Optional[float] = None,
        leader_close_pct: Optional[float] = None,
        note: str = "",
    ) -> OrderEvent:
        """Create an order event for position changes"""
        return OrderEvent(
            event_id=str(uuid.uuid4()),
            portfolio_id=project.portfolio_id,
            exchange=project.exchange,
            trade_account_id=project.trade_account_id or None,
            order_id="",
            trade_id="",
            action=action,
            symbol=symbol,
            position_side=position_side,
            side=side,
            executed_qty=executed_qty,
            avg_price=avg_price,
            order_time=leader_now,
            order_update_time=leader_now,
            leader_delta=leader_delta or 0.0,
            scale=project.scale_value if project.scale_value > 0 else 1.0,
            follower_qty=follower_qty,
            reduce_only=reduce_only,
            order_value=executed_qty * avg_price,
            follower_notional=follower_notional,
            leader_open_pct=leader_open_pct,
            leader_close_pct=leader_close_pct,
            follower_leverage=project.follower_leverage,
            status="queued",
            note=note,
            created_at=leader_now,
        )

    def create_error_event(
        self,
        project: ProjectConfig,
        error_message: str,
        leader_now: int,
    ) -> OrderEvent:
        """Create an error event"""
        return OrderEvent(
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
            note=error_message,
            created_at=leader_now,
        )

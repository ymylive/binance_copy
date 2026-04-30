from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class OrderEvent(BaseModel):
    event_id: str
    portfolio_id: str
    exchange: Optional[str] = None
    leader_id: Optional[str] = None
    account_id: Optional[str] = None
    trade_account_id: Optional[str] = None
    order_id: str
    trade_id: str
    action: str = ""
    symbol: str
    position_side: str
    side: str
    executed_qty: float
    avg_price: float
    order_time: int
    order_update_time: int
    leader_delta: float
    scale: float
    follower_qty: float
    reduce_only: bool
    order_value: float
    follower_notional: Optional[float] = None
    leader_open_pct: Optional[float] = None
    leader_close_pct: Optional[float] = None
    follower_leverage: Optional[float] = None
    status: str
    note: Optional[str] = None
    created_at: int
    executed_at: Optional[int] = None
    latency_ms: Optional[int] = None
    # Mirror lifecycle: join leader-detected signal with follower execution outcome.
    # status above remains the legacy field other code reads (sent/skipped/error/disabled).
    # mirror_* fields are additive: they expose the join key + timing surface for KPIs.
    mirror_status: Literal["pending", "sent", "skipped", "failed"] = "pending"
    mirror_sent_at_ms: Optional[int] = None
    mirror_filled_at_ms: Optional[int] = None
    mirror_latency_ms: Optional[int] = None  # filled_at - leader_detected
    mirror_error: Optional[str] = None

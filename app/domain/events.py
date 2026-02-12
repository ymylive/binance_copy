from __future__ import annotations

from typing import Optional

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

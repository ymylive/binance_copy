from __future__ import annotations

from typing import TYPE_CHECKING, List, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.domain.config import LeaderSubscription


class TradingAccount(BaseModel):
    account_id: str = "default"
    name: str = "Default"
    exchange: Literal["binance", "okx"] = "binance"
    enabled: bool = False
    base_url: str = "https://testnet.binancefuture.com"
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    simulated: bool = False
    recv_window: int = 5000
    timeout_ms: int = 10000
    min_qty: float = 0.0
    max_qty: float = 0.0
    send_position_side: bool = True
    order_type: str = "MARKET"
    time_sync: bool = True
    time_sync_interval_ms: int = 30000
    auto_adjust_qty: bool = True
    min_notional_mode: str = "raise"
    exchange_info_ttl_ms: int = 3600000
    price_ttl_ms: int = 2000
    auto_position_mode: bool = True
    position_mode_ttl_ms: int = 60000
    auto_set_leverage: bool = True
    leverage_ttl_ms: int = 60000
    usdt_order_mode: bool = True
    price_source: str = "mark"
    leader_subscriptions: List["LeaderSubscription"] = Field(default_factory=list)


TradeAccount = TradingAccount


class TradeConfig(BaseModel):
    enabled: bool = False
    default_account_id: str = "default"
    accounts: List[TradingAccount] = Field(default_factory=list)


from .config import LeaderSubscription

TradingAccount.model_rebuild(_types_namespace={"LeaderSubscription": LeaderSubscription})
TradeConfig.model_rebuild(_types_namespace={"LeaderSubscription": LeaderSubscription})

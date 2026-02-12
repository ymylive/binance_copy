from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class QuickProjectInput(BaseModel):
    portfolio_id: str = Field(..., min_length=1)
    enabled: bool = True


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    exchange: Literal["binance", "okx"] = "binance"
    portfolio_id: str = Field(default="", min_length=0)
    leader_id: str = ""
    enabled: bool = True
    monitor_mode: Literal["order_history", "position"] = "position"
    poll_interval_ms: int = 3000
    order_window_ms: int = 1800000
    page_size: int = 5
    scale_mode: Literal[
        "ratio",
        "adaptive",
        "fixed",
        "leader_margin",
        "margin_ratio",
    ] = "margin_ratio"
    scale_value: float = 1.0
    leader_leverage: float = 10.0
    follower_leverage: float = 10.0
    trade_account_id: str = ""
    follower_equity: float = 1000.0
    follower_equity_refresh_ms: int = 30000
    min_qty: float = 0.0
    max_qty: float = 0.0
    detail_refresh_ms: int = 30000
    allocated_equity_pct: float = 100.0


class LeaderSubscription(BaseModel):
    leader_id: str
    enabled: bool = True
    allocated_equity_pct: float = 100.0
    follower_leverage: float = 10.0
    scale_mode: Literal["ratio", "adaptive", "fixed", "leader_margin", "margin_ratio"] = "margin_ratio"
    scale_value: float = 1.0
    monitor_mode: Literal["order_history", "position"] = "position"
    poll_interval_ms: int = 3000


class LeaderConfig(BaseModel):
    leader_id: str
    exchange: Literal["binance", "okx"] = "binance"
    portfolio_id: str = ""
    name: str = ""
    enabled: bool = True


class SignalConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    execute_signals: bool = False
    default_trade_account_id: str = ""
    default_notional_usd: float = 50.0
    default_leverage: float = 10.0
    telegram_bot_token: str = ""
    telegram_chat_ids: List[str] = Field(default_factory=list)
    telegram_poll_interval_ms: int = 5000
    telegram_start_latest: bool = True
    discord_bot_token: str = ""
    discord_channel_ids: List[str] = Field(default_factory=list)
    discord_poll_interval_ms: int = 5000
    discord_start_latest: bool = True
    discord_ignore_bots: bool = True


class OnchainWalletConfig(BaseModel):
    address: str
    enabled: bool = True


class OnchainConfig(BaseModel):
    enabled: bool = False
    chain: Literal["solana"] = "solana"
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    poll_interval_ms: int = 2000
    ignore_mints: List[str] = Field(default_factory=list)
    wallets: List[OnchainWalletConfig] = Field(default_factory=list)


class AppConfig(BaseModel):
    cdp_url: str = "http://127.0.0.1:9222"
    api_base: str = "https://www.binance.com"
    auth_mode: Literal["cdp", "cookie"] = "cookie"
    cookie_path: str = "cookies.json"
    leader_source: Literal["direct", "proxy"] = "direct"
    leader_proxy_base: str = "http://127.0.0.1:8000"
    leader_proxy_timeout_ms: int = 5000
    leader_headers: Dict[str, str] = Field(default_factory=dict)
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    request_timeout_ms: int = 10000
    projects: List[ProjectConfig] = Field(default_factory=list)
    leaders: List[LeaderConfig] = Field(default_factory=list)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    onchain: OnchainConfig = Field(default_factory=OnchainConfig)


class ConfigPatch(BaseModel):
    api_base: Optional[str] = None
    auth_mode: Optional[Literal["cdp", "cookie"]] = None
    cookie_path: Optional[str] = None
    leader_source: Optional[Literal["direct", "proxy"]] = None
    leader_proxy_base: Optional[str] = None
    leader_proxy_timeout_ms: Optional[int] = None
    leader_headers: Optional[Dict[str, str]] = None

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Position:
    """Represents a trading position"""
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.symbol = data.get("symbol", "")
        self.size = float(data.get("positionAmt", 0))
        self.entry_price = float(data.get("entryPrice", 0))
        self.mark_price = float(data.get("markPrice", 0))
        self.unrealized_pnl = float(data.get("unRealizedProfit", 0))
        self.leverage = int(data.get("leverage", 1))


class Order:
    """Represents a trading order"""
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.order_id = data.get("orderId", "")
        self.symbol = data.get("symbol", "")
        self.side = data.get("side", "")
        self.type = data.get("type", "")
        self.price = float(data.get("price", 0))
        self.quantity = float(data.get("origQty", 0))
        self.status = data.get("status", "")
        self.time = data.get("time", 0)


class PortfolioDetail:
    """Represents portfolio details"""
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.equity = float(data.get("totalWalletBalance", 0))
        self.available_balance = float(data.get("availableBalance", 0))
        self.unrealized_pnl = float(data.get("totalUnrealizedProfit", 0))
        self.margin_balance = float(data.get("totalMarginBalance", 0))


class LeaderAdapter(ABC):
    """Abstract source of leader position snapshots and signal events.

    Implementations: BinanceSession, OKXSession, HyperliquidAdapter,
    BiCoinAdapter, SmartMoneyAdapter, ...
    """
    source_name: str = "abstract"  # subclasses override: binance / hyperliquid / etc.

    @abstractmethod
    async def fetch_positions(self, leader_id: str) -> List[Dict[str, Any]]:
        """Return leader's current open positions, normalised dict shape."""
        ...

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """Return adapter health: connected, last_poll_age_ms, last_error."""
        ...

    async def fetch_recent_signals(
        self, leader_id: str, since_ms: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Optional: recent signal events from the source. Default empty."""
        return []

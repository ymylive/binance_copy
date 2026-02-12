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


class ExchangeAdapter(ABC):
    """Abstract base class for exchange adapters"""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the exchange"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the exchange"""
        pass

    @abstractmethod
    async def fetch_positions(self, portfolio_id: str) -> List[Position]:
        """Fetch all positions for a portfolio"""
        pass

    @abstractmethod
    async def fetch_order_history(
        self,
        portfolio_id: str,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Order]:
        """Fetch order history for a portfolio"""
        pass

    @abstractmethod
    async def get_portfolio_detail(self, portfolio_id: str) -> PortfolioDetail:
        """Get portfolio details including balance and equity"""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connection is active"""
        pass

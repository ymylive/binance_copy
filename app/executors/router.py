from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Executor
from .binance import ApiExecutor
from .okx import OKXExecutor
from ..domain.events import OrderEvent


class RoutedExecutor(Executor):
    def __init__(
        self,
        binance: Optional[ApiExecutor] = None,
        okx: Optional[OKXExecutor] = None,
    ) -> None:
        self._binance = binance or ApiExecutor()
        self._okx = okx or OKXExecutor()

    def _resolve_exchange(
        self,
        exchange: Optional[str],
        account_id: Optional[str],
    ) -> str:
        if exchange in {"okx", "binance"}:
            return exchange
        if account_id and self._okx.has_account(account_id):
            return "okx"
        return "binance"

    async def execute(self, event: OrderEvent) -> Dict[str, str]:
        exchange = self._resolve_exchange(event.exchange, event.trade_account_id)
        if exchange == "okx":
            return await self._okx.execute(event)
        return await self._binance.execute(event)

    async def get_follower_equity(self, account_id: Optional[str] = None) -> Optional[float]:
        exchange = self._resolve_exchange(None, account_id)
        if exchange == "okx":
            return await self._okx.get_follower_equity(account_id)
        return await self._binance.get_follower_equity(account_id)

    async def get_follower_balance(
        self,
        account_id: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        exchange = self._resolve_exchange(None, account_id)
        if exchange == "okx":
            return await self._okx.get_follower_balance(account_id)
        return await self._binance.get_follower_balance(account_id)

    async def get_follower_positions(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        exchange = self._resolve_exchange(None, account_id)
        if exchange == "okx":
            return await self._okx.get_follower_positions(account_id)
        return await self._binance.get_follower_positions(account_id)

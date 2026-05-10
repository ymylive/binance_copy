from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Executor
from .binance import ApiExecutor
from .okx import OKXExecutor
from ..core.logging import get_logger
from ..domain.events import OrderEvent
from ..services.config_store import ConfigStore

logger = get_logger()


class RoutedExecutor(Executor):
    def __init__(
        self,
        binance: Optional[ApiExecutor] = None,
        okx: Optional[OKXExecutor] = None,
        config_store: Optional[ConfigStore] = None,
    ) -> None:
        self._binance = binance or ApiExecutor()
        self._okx = okx or OKXExecutor()
        # Lazily-loaded ConfigStore so we can re-read the subscription_enforced
        # flag on every execute() without forcing callers to pass it in. Avoids
        # holding stale state if the operator toggles the flag at runtime.
        self._config_store = config_store or ConfigStore()

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

    def _subscription_blocks(self, account_id: Optional[str]) -> bool:
        """Return True iff subscription enforcement is on AND no active
        Business is bound to this trade account. Failure-open on any error
        (logged) so a corrupted portal store cannot brick live trading."""
        try:
            cfg = self._config_store.load()
        except Exception:
            logger.exception("subscription gate: failed to load AppConfig")
            return False
        if not getattr(cfg, "subscription_enforced", False):
            return False
        try:
            from ..services.portal_store import get_portal_store
            biz = get_portal_store().get_active_business_for_account(account_id or "")
        except Exception:
            logger.exception("subscription gate: portal_store lookup failed")
            return False
        return biz is None

    async def execute(self, event: OrderEvent) -> Dict[str, str]:
        # Subscription gate: when enforcement is on, every follower-side order
        # must map to an active Business. This is the single dispatch seam for
        # both Binance and OKX so guarding here covers all order paths.
        if self._subscription_blocks(event.trade_account_id):
            logger.warning(
                "skip order: no active subscription for account_id=%s event_id=%s",
                event.trade_account_id,
                getattr(event, "event_id", ""),
            )
            event.mirror_status = "skipped"
            event.mirror_error = "subscription_inactive"
            return {
                "status": "skipped",
                "event_id": getattr(event, "event_id", ""),
                "note": "subscription_inactive",
            }
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

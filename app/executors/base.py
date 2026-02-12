from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..domain.events import OrderEvent


class Executor:
    async def execute(self, event: OrderEvent) -> Dict[str, str]:
        raise NotImplementedError

    async def get_follower_equity(self, account_id: Optional[str] = None) -> Optional[float]:
        return None

    async def get_follower_balance(
        self, account_id: Optional[str] = None
    ) -> Optional[Dict[str, float]]:
        return None

    async def get_follower_positions(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

"""Binance Smart Money adapter — wallet-tracking signal source.

Status: pending. Adapter scaffold only; real implementation requires
Binance Smart Money wallet feed integration (HTTP + websocket fanout).
"""
from typing import Any, Dict, List

from .base import LeaderAdapter


class SmartMoneyAdapter(LeaderAdapter):
    source_name = "binance-sm"

    def __init__(self, wallet_address: str) -> None:
        self.wallet_address = wallet_address

    async def fetch_positions(self, leader_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("smart-money adapter not yet implemented")

    async def health(self) -> Dict[str, Any]:
        return {
            "connected": False,
            "status": "pending_implementation",
            "source": self.source_name,
        }

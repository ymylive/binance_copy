"""Hyperliquid adapter — decentralized perp signal source.

Status: pending. Adapter scaffold only; real implementation requires
hyperliquid public API integration (HTTP info endpoint + websocket).
"""
from typing import Any, Dict, List

from .base import LeaderAdapter


class HyperliquidAdapter(LeaderAdapter):
    source_name = "hyperliquid"

    def __init__(self, address: str, api_url: str = "https://api.hyperliquid.xyz") -> None:
        self.address = address
        self.api_url = api_url

    async def fetch_positions(self, leader_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("hyperliquid adapter not yet implemented")

    async def health(self) -> Dict[str, Any]:
        return {
            "connected": False,
            "status": "pending_implementation",
            "source": self.source_name,
        }

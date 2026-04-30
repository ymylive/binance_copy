"""BiCoin adapter — share-link based copy trade signal source.

Status: pending. Adapter scaffold only; real implementation requires
parsing the BiCoin share-link landing payload + ongoing polling.
"""
from typing import Any, Dict, List

from .base import LeaderAdapter


class BiCoinAdapter(LeaderAdapter):
    source_name = "bicoin"

    def __init__(self, share_link: str) -> None:
        self.share_link = share_link

    async def fetch_positions(self, leader_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("bicoin adapter not yet implemented")

    async def health(self) -> Dict[str, Any]:
        return {
            "connected": False,
            "status": "pending_implementation",
            "source": self.source_name,
        }

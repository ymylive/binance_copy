from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class OnchainEvent(BaseModel):
    chain: Literal["solana"] = "solana"
    wallet: str
    signature: str
    mint: str
    direction: Literal["buy", "sell"]
    token_change: float
    sol_change: float
    timestamp: int

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class OKXTradeAccount(BaseModel):
    account_id: str = "default"
    name: str = "Default"
    enabled: bool = False
    base_url: str = "https://www.okx.com"
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    simulated: bool = False
    timeout_ms: int = 10000
    auto_set_leverage: bool = True
    leverage_ttl_ms: int = 60000


class OKXTradeConfig(BaseModel):
    enabled: bool = False
    default_account_id: str = "default"
    accounts: List[OKXTradeAccount] = Field(default_factory=list)

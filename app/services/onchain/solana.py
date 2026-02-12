from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import httpx

from ...core.logging import get_logger
from ...core.time import now_ms
from ...domain.onchain import OnchainEvent

logger = get_logger()

DEFAULT_IGNORE_MINTS = {
    "So11111111111111111111111111111111111111112",  # WSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}


class SolanaWatcher:
    def __init__(
        self,
        rpc_url: str,
        wallet: str,
        poll_interval_ms: int,
        ignore_mints: Iterable[str],
        event_sink: Callable[[OnchainEvent], None],
    ) -> None:
        self._rpc_url = rpc_url
        self._wallet = wallet
        self._poll_interval = max(poll_interval_ms, 500) / 1000.0
        self._ignore_mints = set(ignore_mints) | DEFAULT_IGNORE_MINTS
        self._event_sink = event_sink
        self._running = False
        self._last_signature: Optional[str] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        while self._running:
            try:
                await self._poll_once()
            except Exception:
                logger.exception("solana watcher error wallet=%s", self._wallet)
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._running = False

    async def _poll_once(self) -> None:
        signatures = await self._fetch_signatures(limit=20)
        if not signatures:
            return
        latest = signatures[0]
        if not self._last_signature:
            self._last_signature = latest
            return
        new_signatures: List[str] = []
        for entry in signatures:
            if entry == self._last_signature:
                break
            new_signatures.append(entry)
        if not new_signatures:
            return
        self._last_signature = latest
        for signature in reversed(new_signatures):
            await self._process_signature(signature)

    async def _fetch_signatures(self, limit: int = 20) -> List[str]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [self._wallet, {"limit": limit}],
        }
        timeout = 10.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self._rpc_url, json=payload)
        data = resp.json()
        result = data.get("result") or []
        signatures = []
        for item in result:
            sig = item.get("signature")
            if sig:
                signatures.append(sig)
        return signatures

    async def _fetch_transaction(self, signature: str) -> Optional[Dict[str, Any]]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }
        timeout = 15.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self._rpc_url, json=payload)
        data = resp.json()
        return data.get("result")

    async def _process_signature(self, signature: str) -> None:
        tx = await self._fetch_transaction(signature)
        if not tx:
            return
        event = self._parse_transaction(signature, tx)
        if event:
            self._event_sink(event)

    def _parse_transaction(self, signature: str, tx: Dict[str, Any]) -> Optional[OnchainEvent]:
        meta = tx.get("meta") or {}
        pre_tokens = meta.get("preTokenBalances") or []
        post_tokens = meta.get("postTokenBalances") or []
        if not pre_tokens and not post_tokens:
            return None

        token_changes: Dict[str, Tuple[float, int]] = {}
        decimals_map: Dict[str, int] = {}

        def _apply(balance_list: List[Dict[str, Any]], sign: int) -> None:
            for item in balance_list:
                if item.get("owner") != self._wallet:
                    continue
                mint = item.get("mint")
                if not mint or mint in self._ignore_mints:
                    continue
                ui = item.get("uiTokenAmount") or {}
                amount_str = ui.get("amount") or "0"
                decimals = int(ui.get("decimals") or 0)
                try:
                    raw = int(amount_str)
                except (TypeError, ValueError):
                    raw = 0
                token_changes[mint] = (token_changes.get(mint, (0.0, decimals))[0] + sign * raw, decimals)
                decimals_map[mint] = decimals

        _apply(pre_tokens, -1)
        _apply(post_tokens, 1)

        if not token_changes:
            return None

        mint, (raw_change, decimals) = max(
            token_changes.items(),
            key=lambda item: abs(item[1][0]),
        )
        if raw_change == 0:
            return None

        token_change = raw_change / (10 ** decimals) if decimals else float(raw_change)
        direction = "buy" if token_change > 0 else "sell"

        sol_change = self._resolve_sol_change(tx)
        block_time = tx.get("blockTime") or 0
        timestamp = int(block_time * 1000) if block_time else now_ms()

        return OnchainEvent(
            chain="solana",
            wallet=self._wallet,
            signature=signature,
            mint=mint,
            direction=direction,
            token_change=abs(token_change),
            sol_change=sol_change,
            timestamp=timestamp,
        )

    def _resolve_sol_change(self, tx: Dict[str, Any]) -> float:
        meta = tx.get("meta") or {}
        pre_balances = meta.get("preBalances") or []
        post_balances = meta.get("postBalances") or []
        account_keys = (tx.get("transaction") or {}).get("message", {}).get("accountKeys") or []
        wallet_index = None
        for idx, entry in enumerate(account_keys):
            if isinstance(entry, str) and entry == self._wallet:
                wallet_index = idx
                break
            if isinstance(entry, dict) and entry.get("pubkey") == self._wallet:
                wallet_index = idx
                break
        if wallet_index is None:
            return 0.0
        try:
            pre = int(pre_balances[wallet_index])
            post = int(post_balances[wallet_index])
        except (IndexError, TypeError, ValueError):
            return 0.0
        return (post - pre) / 1e9

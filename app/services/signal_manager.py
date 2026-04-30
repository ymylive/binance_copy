from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional

import httpx

from ..core.logging import get_logger
from ..core.time import now_ms
from ..domain.config import SignalConfig
from ..domain.events import OrderEvent
from ..executors.base import Executor

logger = get_logger()


@dataclass
class ParsedSignal:
    symbol: str
    side: str
    position_side: str
    leverage: Optional[float]
    notional: Optional[float]
    action: str = "open"


class SignalManager:
    def __init__(
        self,
        config: SignalConfig,
        executor: Executor,
        event_sink: Callable[[OrderEvent], None],
    ) -> None:
        self._config = config
        self._executor = executor
        self._event_sink = event_sink
        self._tasks: list[asyncio.Task] = []
        self._client: Optional[httpx.AsyncClient] = None
        self._telegram_offset: Optional[int] = None
        self._discord_last_ids: Dict[str, str] = {}

    async def start(self) -> None:
        if not self._config.enabled:
            return
        self._client = httpx.AsyncClient(timeout=10.0)
        if self._config.telegram_bot_token and self._config.telegram_chat_ids:
            self._tasks.append(asyncio.create_task(self._telegram_loop()))
        if self._config.discord_bot_token and self._config.discord_channel_ids:
            self._tasks.append(asyncio.create_task(self._discord_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _telegram_loop(self) -> None:
        token = self._config.telegram_bot_token
        chat_ids = {str(cid) for cid in self._config.telegram_chat_ids}
        interval = max(self._config.telegram_poll_interval_ms, 1000) / 1000.0
        if self._config.telegram_start_latest:
            await self._prime_telegram_offset(token)
        while True:
            try:
                updates = await self._get_telegram_updates(token)
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        self._telegram_offset = update_id + 1
                    message = update.get("message") or update.get("channel_post") or {}
                    chat_id = str((message.get("chat") or {}).get("id") or "")
                    if chat_id and chat_ids and chat_id not in chat_ids:
                        continue
                    text = message.get("text") or message.get("caption") or ""
                    if text:
                        await self._handle_signal(
                            text,
                            source="telegram",
                            source_id=str(message.get("message_id") or update_id or ""),
                        )
            except Exception:
                logger.exception("telegram signal loop failed")
            await asyncio.sleep(interval)

    async def _discord_loop(self) -> None:
        token = self._config.discord_bot_token
        channel_ids = [str(cid) for cid in self._config.discord_channel_ids]
        interval = max(self._config.discord_poll_interval_ms, 1000) / 1000.0
        while True:
            try:
                for channel_id in channel_ids:
                    await self._poll_discord_channel(token, channel_id)
            except Exception:
                logger.exception("discord signal loop failed")
            await asyncio.sleep(interval)

    async def _prime_telegram_offset(self, token: str) -> None:
        updates = await self._get_telegram_updates(token, limit=1)
        if updates:
            update_id = updates[-1].get("update_id")
            if isinstance(update_id, int):
                self._telegram_offset = update_id + 1

    async def _get_telegram_updates(self, token: str, limit: int = 50) -> list[Dict[str, object]]:
        client = self._require_client()
        params = {"limit": limit}
        if self._telegram_offset is not None:
            params["offset"] = self._telegram_offset
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        resp = await client.get(url, params=params)
        if not resp.is_success:
            logger.warning("telegram getUpdates failed status=%s", resp.status_code)
            return []
        data = resp.json()
        if not isinstance(data, dict) or not data.get("ok"):
            return []
        updates = data.get("result") or []
        return updates if isinstance(updates, list) else []

    async def _poll_discord_channel(self, token: str, channel_id: str) -> None:
        client = self._require_client()
        headers = {"Authorization": f"Bot {token}"}
        params: Dict[str, object] = {"limit": 50}
        last_id = self._discord_last_ids.get(channel_id)
        if last_id:
            params["after"] = last_id
        elif self._config.discord_start_latest:
            params["limit"] = 1
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        resp = await client.get(url, headers=headers, params=params)
        if not resp.is_success:
            logger.warning(
                "discord channel fetch failed channel=%s status=%s",
                channel_id,
                resp.status_code,
            )
            return
        messages = resp.json()
        if not isinstance(messages, list):
            return
        if not messages:
            return
        if self._config.discord_start_latest and not last_id:
            newest = messages[0].get("id")
            if newest:
                self._discord_last_ids[channel_id] = str(newest)
            return
        for msg in reversed(messages):
            msg_id = str(msg.get("id") or "")
            if not msg_id:
                continue
            self._discord_last_ids[channel_id] = msg_id
            content = str(msg.get("content") or "")
            if not content:
                continue
            if msg.get("author", {}).get("bot") and self._config.discord_ignore_bots:
                continue
            await self._handle_signal(content, source="discord", source_id=msg_id)

    async def _handle_signal(self, text: str, source: str, source_id: str) -> None:
        parsed = parse_signal(text, self._config)
        if not parsed:
            return
        event = self._build_event(parsed, source, source_id)
        self._event_sink(event)
        if not self._config.execute_signals:
            logger.info("signal parsed source=%s id=%s symbol=%s side=%s dry_run=true",
                        source, source_id, parsed.symbol, parsed.side)
            return
        try:
            result = await self._executor.execute(event)
            logger.info("signal executed source=%s id=%s status=%s",
                        source, source_id, result.get("status"))
        except Exception:
            logger.exception("signal execution failed source=%s id=%s", source, source_id)

    def _build_event(self, signal: ParsedSignal, source: str, source_id: str) -> OrderEvent:
        now = now_ms()
        notional = signal.notional or self._config.default_notional_usd
        leverage = signal.leverage or self._config.default_leverage
        base_qty = 1.0 if signal.side == "BUY" else -1.0
        order_value = float(notional or 0.0)
        return OrderEvent(
            event_id=f"sig-{source}-{source_id}-{now}",
            portfolio_id=f"signal-{source}",
            exchange="binance",
            leader_id=None,
            account_id=None,
            trade_account_id=self._config.default_trade_account_id or None,
            order_id=f"SIG-{source_id}",
            trade_id=f"SIG-{source_id}",
            action=signal.action,
            symbol=signal.symbol,
            position_side=signal.position_side,
            side=signal.side,
            executed_qty=abs(base_qty),
            avg_price=0.0,
            order_time=now,
            order_update_time=now,
            leader_delta=base_qty,
            scale=1.0,
            follower_qty=base_qty,
            reduce_only=False,
            order_value=order_value,
            follower_notional=order_value,
            leader_open_pct=None,
            leader_close_pct=None,
            follower_leverage=leverage,
            status="queued",
            note=f"signal:{source}",
            created_at=now,
        )

    def _require_client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("signal manager client not initialized")
        return self._client


def parse_signal(text: str, config: SignalConfig) -> Optional[ParsedSignal]:
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None
    symbol = _parse_symbol(raw)
    if not symbol:
        return None
    side, position_side = _parse_side(raw)
    if not side:
        return None
    leverage = _parse_leverage(raw)
    notional = _parse_notional(raw)
    return ParsedSignal(
        symbol=symbol,
        side=side,
        position_side=position_side,
        leverage=leverage,
        notional=notional,
    )


def _parse_symbol(text: str) -> str:
    pairs = ("USDT", "BUSD", "USDC", "USD")
    for quote in pairs:
        match = re.search(rf"\b([A-Z]{{2,10}})\s*[-/]?\s*{quote}\b", text, re.IGNORECASE)
        if match:
            base = match.group(1).upper()
            return f"{base}{quote}"
    return ""


def _parse_side(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if "long" in lowered or re.search(r"\bbuy\b", lowered):
        return "BUY", "LONG"
    if "short" in lowered or re.search(r"\bsell\b", lowered):
        return "SELL", "SHORT"
    return "", ""


def _parse_leverage(text: str) -> Optional[float]:
    match = re.search(r"(\d{1,3})\s*x", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    match = re.search(r"leverage\s*[:=]?\s*(\d{1,3})", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _parse_notional(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(usdt|usd|\$)\b", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    match = re.search(r"(?:size|amount)\s*[:=]?\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

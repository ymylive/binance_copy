"""Multi-channel notification dispatcher for trade events.

Despite the legacy file name (`telegram_notifier`) this module owns ALL
outbound trade-event notifications. It:

  * subscribes once to `state.subscribe_signals()` on app startup
  * tracks running average-open / realised-PnL per (leader, symbol, side)
  * formats each event in the configured language (zh / en)
  * batches bursts: same (leader, symbol, action) inside `batchWindowSec`
    coalesces into a single message instead of flooding the channel
  * fans out to every enabled channel: Telegram (with inline keyboard),
    Dingtalk, Feishu, Discord — each with its own payload shape

Config persists at `runtime/portal/telegram_config.json` and is fully
admin-managed via `/api/portal/admin/telegram/{config,test}`. The token /
webhook fields are masked in GET responses; submit empty strings to keep
the existing secret unchanged.

No new pip deps; uses httpx already in `requirements.txt`.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from ..core.logging import get_logger
from ..core.paths import ROOT_DIR

logger = get_logger()

CONFIG_PATH = ROOT_DIR / "runtime" / "portal" / "telegram_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    # Telegram
    "botToken": "",
    "chatIds": [],
    # Per-event filtering
    "notifyAdminSignals": True,
    "notifyAutoSignals": True,
    "includePnl": True,
    # Multi-channel webhooks
    "dingtalkWebhook": "",
    "feishuWebhook": "",
    "discordWebhook": "",
    # Localisation
    "language": "zh",  # "zh" | "en"
    # Burst batching: same (leader|symbol|action) within this window collapses
    # into the latest message. 0 disables.
    "batchWindowSec": 3,
    # Optional: link prefix used by the inline button. Defaults to /admin.
    "consoleBaseUrl": "",
}

# Channel keys masked in GET responses to avoid leaking secrets.
_MASKED_KEYS = ("botToken", "dingtalkWebhook", "feishuWebhook", "discordWebhook")


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return "***"
    return value[:6] + "…" + value[-4:]


# ---- i18n -------------------------------------------------------------
_LABELS: Dict[str, Dict[str, str]] = {
    "zh": {
        "title_open":   "🟢 开仓",
        "title_add":    "🔵 加仓",
        "title_reduce": "🟡 减仓",
        "title_close":  "🔴 平仓",
        "field_time":   "时间",
        "field_side":   "方向",
        "field_price":  "成交价",
        "field_qty":    "成交量",
        "field_avg":    "当前均价",
        "field_pnl":    "本笔盈亏",
        "field_cum":    "累计盈亏",
        "field_left":   "持仓余量",
        "field_leader": "交易员",
        "field_ex":     "交易所",
        "from_admin":   "来源: 管理员注入",
        "test_title":   "korincoin · 通道测试",
        "test_body":    "若收到此消息,表示通道已配置就绪。",
        "btn_view":     "🔍 查看详情",
        "btn_chart":    "📈 走势",
        "burst_n":      "(合并 {n} 条)",
    },
    "en": {
        "title_open":   "🟢 OPEN",
        "title_add":    "🔵 ADD",
        "title_reduce": "🟡 REDUCE",
        "title_close":  "🔴 CLOSE",
        "field_time":   "Time",
        "field_side":   "Side",
        "field_price":  "Fill price",
        "field_qty":    "Fill size",
        "field_avg":    "Avg open",
        "field_pnl":    "Realised PnL",
        "field_cum":    "Cumulative PnL",
        "field_left":   "Remaining size",
        "field_leader": "Leader",
        "field_ex":     "Exchange",
        "from_admin":   "Source: admin inject",
        "test_title":   "korincoin · channel probe",
        "test_body":    "If you see this, the channel is correctly wired.",
        "btn_view":     "🔍 Details",
        "btn_chart":    "📈 Chart",
        "burst_n":      "(coalesced {n})",
    },
}


def L(lang: str, key: str, **fmt: Any) -> str:
    table = _LABELS.get(lang) or _LABELS["zh"]
    text = table.get(key) or _LABELS["zh"].get(key) or key
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text


class TelegramNotifier:
    """Singleton multi-channel dispatcher (legacy class name kept for
    backward compatibility with /api/portal/admin/telegram/* routes)."""

    _instance: Optional["TelegramNotifier"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._task: Optional[asyncio.Task] = None
        self._queue: Optional[asyncio.Queue] = None
        # PnL state: key = leader|symbol|positionSide
        self._positions: Dict[str, Dict[str, float]] = {}
        # Burst coalescing buffer: key -> {first_at, count, latest_event}
        self._burst: Dict[str, Dict[str, Any]] = {}
        self._burst_flush_task: Optional[asyncio.Task] = None
        self._load_config()

    # ---- config ---------------------------------------------------
    def _load_config(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            if CONFIG_PATH.is_file():
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    merged = dict(DEFAULT_CONFIG)
                    merged.update(raw)
                    self._config = merged
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("notifier: config load failed: %s", exc)

    def _save_config(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._config, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, CONFIG_PATH)
        except OSError as exc:
            logger.error("notifier: config save failed: %s", exc)

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            cfg = dict(self._config)
            for k in _MASKED_KEYS:
                cfg[k] = _mask(cfg.get(k) or "")
            return cfg

    def update_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            for key, value in patch.items():
                if key not in DEFAULT_CONFIG:
                    continue
                # For masked secrets the key is OMITTED (None) → "keep
                # current". An explicit empty string CLEARS the value.
                # Front-end sends None when the password input is left blank
                # by passing payload.model_dump(exclude_none=True) at the
                # router; an explicit "" arrives only when the operator
                # actively cleared the field.
                if key in _MASKED_KEYS and value is None:
                    continue
                if key == "chatIds":
                    if not isinstance(value, list):
                        continue
                    self._config[key] = [str(c).strip() for c in value if str(c).strip()]
                elif key in {"enabled", "notifyAdminSignals", "notifyAutoSignals", "includePnl"}:
                    self._config[key] = bool(value)
                elif key == "language":
                    self._config[key] = "en" if str(value).lower().startswith("en") else "zh"
                elif key == "batchWindowSec":
                    try:
                        self._config[key] = max(0, min(60, int(value)))
                    except (TypeError, ValueError):
                        continue
                else:
                    self._config[key] = str(value).strip()
            self._save_config()
            return self.get_config()

    # ---- HTTP helpers --------------------------------------------
    async def _post_json(self, url: str, body: Dict[str, Any], timeout: float = 8.0) -> Tuple[bool, str]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=body)
                if resp.status_code == 200:
                    return True, ""
                return False, f"HTTP {resp.status_code}: {resp.text[:160]}"
        except Exception as exc:
            return False, str(exc)

    # ---- Channel adapters ----------------------------------------
    async def _send_telegram(self, text: str, buttons: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        cfg = self._config
        token = cfg.get("botToken") or ""
        chat_ids = list(cfg.get("chatIds") or [])
        if not token or not chat_ids:
            return {"sent": 0, "failed": 0, "skipped": "telegram-missing-config"}
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        sent = failed = 0
        for cid in chat_ids:
            body: Dict[str, Any] = {
                "chat_id": cid,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            if buttons:
                body["reply_markup"] = {"inline_keyboard": buttons}
            ok, err = await self._post_json(url, body)
            if ok:
                sent += 1
            else:
                failed += 1
                logger.warning("telegram: chat=%s failed: %s", cid, err)
        return {"sent": sent, "failed": failed}

    async def _send_dingtalk(self, title: str, text: str) -> Dict[str, Any]:
        url = self._config.get("dingtalkWebhook") or ""
        if not url:
            return {"skipped": "dingtalk-missing"}
        body = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }
        ok, err = await self._post_json(url, body)
        if not ok:
            logger.warning("dingtalk: failed: %s", err)
        return {"sent": 1 if ok else 0, "failed": 0 if ok else 1}

    async def _send_feishu(self, title: str, text: str) -> Dict[str, Any]:
        url = self._config.get("feishuWebhook") or ""
        if not url:
            return {"skipped": "feishu-missing"}
        # Feishu's "interactive" card schema for richer formatting.
        body = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "turquoise",
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": text}},
                ],
            },
        }
        ok, err = await self._post_json(url, body)
        if not ok:
            logger.warning("feishu: failed: %s", err)
        return {"sent": 1 if ok else 0, "failed": 0 if ok else 1}

    async def _send_discord(self, title: str, text: str) -> Dict[str, Any]:
        url = self._config.get("discordWebhook") or ""
        if not url:
            return {"skipped": "discord-missing"}
        # Discord webhook accepts an embed list; we send one rich embed
        # whose description carries the same Markdown body.
        body = {
            "username": "korincoin",
            "embeds": [
                {
                    "title": title,
                    "description": text,
                    "color": 0x17A697,
                }
            ],
        }
        ok, err = await self._post_json(url, body)
        if not ok:
            logger.warning("discord: failed: %s", err)
        return {"sent": 1 if ok else 0, "failed": 0 if ok else 1}

    # ---- formatting -----------------------------------------------
    def _track_position(self, event: Any) -> Optional[Dict[str, float]]:
        try:
            leader = event.leader_id or event.portfolio_id or "?"
            sym = (event.symbol or "").upper()
            ps = (event.position_side or "").upper()
            key = f"{leader}|{sym}|{ps}"
            qty = float(event.executed_qty or 0.0)
            price = float(event.avg_price or 0.0)
            action = (event.action or "").lower()
        except Exception:
            return None
        with self._lock:
            pos = self._positions.get(key) or {"size": 0.0, "avg_open": 0.0, "cum_pnl": 0.0}
            realised_pnl = 0.0
            if action in ("open", "add"):
                new_size = pos["size"] + qty
                if new_size > 0:
                    pos["avg_open"] = (pos["avg_open"] * pos["size"] + price * qty) / new_size
                pos["size"] = new_size
            elif action in ("reduce", "close"):
                close_qty = qty if action == "reduce" else max(qty, pos["size"])
                if pos["size"] > 0 and pos["avg_open"] > 0:
                    is_long = ps == "LONG" or (ps not in ("LONG", "SHORT") and (event.side or "").upper() == "BUY")
                    if is_long:
                        realised_pnl = (price - pos["avg_open"]) * close_qty
                    else:
                        realised_pnl = (pos["avg_open"] - price) * close_qty
                pos["size"] = max(0.0, pos["size"] - close_qty)
                pos["cum_pnl"] += realised_pnl
                if pos["size"] <= 1e-9:
                    pos["avg_open"] = 0.0
            self._positions[key] = pos
            return {
                "avg_open": pos["avg_open"],
                "size_after": pos["size"],
                "realised_pnl": realised_pnl,
                "cum_pnl": pos["cum_pnl"],
                "key": key,
            }

    def _title_for(self, lang: str, action: str) -> str:
        return L(lang, f"title_{(action or '').lower()}") or action.upper()

    def format_event(self, event: Any, *, batch_count: int = 1) -> Tuple[str, str]:
        """Returns (title, body_markdown) for the given event."""
        cfg = self._config
        lang = cfg.get("language") or "zh"
        track = self._track_position(event) or {}
        action = (event.action or "").lower()
        sym = event.symbol or "—"
        side = (event.side or "").upper()
        ps = (event.position_side or "").upper()
        qty = float(event.executed_qty or 0.0)
        price = float(event.avg_price or 0.0)
        leader = event.leader_id or event.portfolio_id or "—"
        exchange = event.exchange or "—"
        note = event.note or ""
        is_admin = note.startswith("[admin:")
        ts_ms = event.created_at or int(time.time() * 1000)
        ts = time.strftime("%m-%d %H:%M:%S", time.localtime(ts_ms / 1000))

        title_label = self._title_for(lang, action)
        title = f"{title_label} · {sym}"
        if batch_count > 1:
            title += " " + L(lang, "burst_n", n=batch_count)

        lines: List[str] = []
        lines.append(f"*{title}*")
        lines.append(f"`{L(lang, 'field_time')}`: {ts}")
        lines.append(f"`{L(lang, 'field_side')}`: {side or '—'} ({ps or '—'})")
        lines.append(f"`{L(lang, 'field_price')}`: {price:,.4f}")
        lines.append(f"`{L(lang, 'field_qty')}`: {qty:,.4f}")
        if track.get("avg_open"):
            lines.append(f"`{L(lang, 'field_avg')}`: {track['avg_open']:,.4f}")
        if action in ("reduce", "close") and cfg.get("includePnl", True):
            rp = track.get("realised_pnl") or 0.0
            cp = track.get("cum_pnl") or 0.0
            arrow = "📈" if rp >= 0 else "📉"
            lines.append(f"`{L(lang, 'field_pnl')}`: {arrow} {rp:+,.4f}")
            lines.append(f"`{L(lang, 'field_cum')}`: {cp:+,.4f}")
        if track.get("size_after") is not None and action != "close":
            lines.append(f"`{L(lang, 'field_left')}`: {track['size_after']:,.4f}")
        lines.append(f"`{L(lang, 'field_leader')}`: `{leader}`")
        lines.append(f"`{L(lang, 'field_ex')}`: {exchange}")
        if is_admin:
            lines.append(f"_{L(lang, 'from_admin')}_")
        return title, "\n".join(lines)

    def _telegram_buttons(self, event: Any) -> List[List[Dict[str, Any]]]:
        cfg = self._config
        lang = cfg.get("language") or "zh"
        sym = (event.symbol or "").upper()
        leader = event.leader_id or event.portfolio_id or ""
        base = (cfg.get("consoleBaseUrl") or "").rstrip("/")
        details_url = f"{base}/admin#signals" if base else "https://copy.cornna.xyz/admin#signals"
        # TradingView quick chart for a known symbol (BTCUSDT etc).
        chart_url = f"https://www.tradingview.com/symbols/{quote_plus(sym)}/"
        row1 = [
            {"text": L(lang, "btn_view"), "url": details_url},
            {"text": L(lang, "btn_chart"), "url": chart_url},
        ]
        return [row1]

    # ---- batching + dispatch -------------------------------------
    async def _dispatch(self, event: Any, batch_count: int = 1) -> Dict[str, Any]:
        cfg = self._config
        title, body = self.format_event(event, batch_count=batch_count)
        results: Dict[str, Any] = {}
        # Telegram (with buttons)
        if cfg.get("botToken"):
            buttons = self._telegram_buttons(event)
            results["telegram"] = await self._send_telegram(body, buttons)
        # Webhook channels reuse the same markdown body.
        if cfg.get("dingtalkWebhook"):
            results["dingtalk"] = await self._send_dingtalk(title, body)
        if cfg.get("feishuWebhook"):
            results["feishu"] = await self._send_feishu(title, body)
        if cfg.get("discordWebhook"):
            results["discord"] = await self._send_discord(title, body)
        return results

    async def _flush_burst_after(self, key: str, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        with self._lock:
            entry = self._burst.pop(key, None)
        if not entry:
            return
        try:
            await self._dispatch(entry["evt"], batch_count=entry["count"])
        except Exception:
            logger.exception("notifier: flush failed for key=%s", key)

    async def _maybe_batch_or_dispatch(self, event: Any) -> None:
        cfg = self._config
        window = int(cfg.get("batchWindowSec") or 0)
        if window <= 0:
            await self._dispatch(event, batch_count=1)
            return
        try:
            leader = event.leader_id or event.portfolio_id or "?"
            sym = (event.symbol or "").upper()
            action = (event.action or "").lower()
            key = f"{leader}|{sym}|{action}"
        except Exception:
            await self._dispatch(event, batch_count=1)
            return
        with self._lock:
            existing = self._burst.get(key)
            if existing:
                existing["count"] += 1
                existing["evt"] = event  # keep the latest one as the representative
                return
            self._burst[key] = {"count": 1, "evt": event, "first_at": time.time()}
        # First occurrence in the window: schedule a flush.
        asyncio.create_task(self._flush_burst_after(key, float(window)))

    # ---- one-shot send (test endpoint) --------------------------
    async def send_test(self, chat_id: Optional[str] = None) -> Dict[str, Any]:
        cfg = self._config
        lang = cfg.get("language") or "zh"
        title = L(lang, "test_title")
        body = (
            f"*{title}*\n"
            f"`{L(lang, 'field_time')}`: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{L(lang, 'test_body')}"
        )
        results: Dict[str, Any] = {}
        if cfg.get("botToken"):
            if chat_id:
                # One-shot to a single chat ignoring chatIds list.
                url = f"https://api.telegram.org/bot{cfg['botToken']}/sendMessage"
                ok, err = await self._post_json(url, {
                    "chat_id": str(chat_id),
                    "text": body,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                })
                results["telegram"] = {"sent": 1 if ok else 0, "failed": 0 if ok else 1, "error": err}
            else:
                results["telegram"] = await self._send_telegram(body, [])
        if cfg.get("dingtalkWebhook"):
            results["dingtalk"] = await self._send_dingtalk(title, body)
        if cfg.get("feishuWebhook"):
            results["feishu"] = await self._send_feishu(title, body)
        if cfg.get("discordWebhook"):
            results["discord"] = await self._send_discord(title, body)
        if not results:
            return {"ok": False, "reason": "no channel configured"}
        # ok if at least one channel actually delivered
        any_ok = any((r.get("sent", 0) or 0) > 0 for r in results.values())
        return {"ok": any_ok, "channels": results}

    # ---- consumer loop -------------------------------------------
    async def _consumer_loop(self, state) -> None:
        self._queue = state.subscribe_signals()
        logger.info("notifier: subscriber started")
        try:
            while True:
                evt = await self._queue.get()
                if not self._config.get("enabled"):
                    continue
                note = (getattr(evt, "note", None) or "")
                is_admin = note.startswith("[admin:")
                if is_admin and not self._config.get("notifyAdminSignals", True):
                    continue
                if not is_admin and not self._config.get("notifyAutoSignals", True):
                    continue
                try:
                    await self._maybe_batch_or_dispatch(evt)
                except Exception:
                    logger.exception("notifier: dispatch step failed")
        except asyncio.CancelledError:
            raise
        finally:
            try:
                state.unsubscribe_signals(self._queue)
            except Exception:
                pass
            self._queue = None

    def start(self, state) -> None:
        if self._task and not self._task.done():
            return
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop is None or not loop.is_running():
            return
        self._task = loop.create_task(self._consumer_loop(state))


def get_notifier() -> TelegramNotifier:
    if TelegramNotifier._instance is None:
        with TelegramNotifier._instance_lock:
            if TelegramNotifier._instance is None:
                TelegramNotifier._instance = TelegramNotifier()
    return TelegramNotifier._instance


__all__ = ["TelegramNotifier", "get_notifier"]

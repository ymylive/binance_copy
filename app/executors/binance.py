from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from ..core.logging import get_logger
from ..core.paths import TRADE_CONFIG_PATH
from ..core.time import now_ms
from ..domain.events import OrderEvent
from ..domain.trade import TradeAccount, TradeConfig
from .base import Executor

logger = get_logger()
MARGIN_TOLERANCE_USDT = 1.0


def load_trade_config() -> TradeConfig:
    if TRADE_CONFIG_PATH.exists():
        try:
            data = json.loads(TRADE_CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            logger.warning("trade_config.json invalid json error=%s", exc)
            return TradeConfig(accounts=[TradeAccount()])
        if not isinstance(data, dict):
            logger.warning("trade_config.json unexpected format type=%s", type(data).__name__)
            return TradeConfig(accounts=[TradeAccount()])
        if data.get("accounts"):
            try:
                return TradeConfig.model_validate(data)
            except ValidationError as exc:
                logger.warning("trade_config.json validation failed error=%s", exc)
                return TradeConfig(accounts=[TradeAccount()])
        try:
            account = TradeAccount(
                account_id="default",
                name="Default",
                enabled=bool(data.get("enabled", False)),
                base_url=str(data.get("base_url") or TradeAccount().base_url),
                api_key=str(data.get("api_key") or ""),
                api_secret=str(data.get("api_secret") or ""),
                passphrase=str(data.get("passphrase") or ""),
                simulated=bool(data.get("simulated", False)),
                recv_window=int(data.get("recv_window") or TradeAccount().recv_window),
                timeout_ms=int(data.get("timeout_ms") or TradeAccount().timeout_ms),
                min_qty=float(data.get("min_qty") or 0.0),
                max_qty=float(data.get("max_qty") or 0.0),
                send_position_side=bool(data.get("send_position_side", True)),
                order_type=str(data.get("order_type") or TradeAccount().order_type),
                time_sync=bool(data.get("time_sync", True)),
                time_sync_interval_ms=int(
                    data.get("time_sync_interval_ms") or TradeAccount().time_sync_interval_ms
                ),
                auto_adjust_qty=bool(data.get("auto_adjust_qty", True)),
                min_notional_mode=str(data.get("min_notional_mode") or "raise"),
                exchange_info_ttl_ms=int(
                    data.get("exchange_info_ttl_ms") or TradeAccount().exchange_info_ttl_ms
                ),
                price_ttl_ms=int(data.get("price_ttl_ms") or TradeAccount().price_ttl_ms),
                auto_position_mode=bool(data.get("auto_position_mode", True)),
                position_mode_ttl_ms=int(
                    data.get("position_mode_ttl_ms") or TradeAccount().position_mode_ttl_ms
                ),
                auto_set_leverage=bool(data.get("auto_set_leverage", True)),
                leverage_ttl_ms=int(data.get("leverage_ttl_ms") or TradeAccount().leverage_ttl_ms),
                usdt_order_mode=bool(data.get("usdt_order_mode", True)),
                price_source=str(data.get("price_source") or TradeAccount().price_source),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("trade_config.json legacy parse failed error=%s", exc)
            return TradeConfig(accounts=[TradeAccount()])
        return TradeConfig(
            enabled=bool(data.get("enabled", False)),
            default_account_id="default",
            accounts=[account],
        )
    return TradeConfig(accounts=[TradeAccount()])


def save_trade_config(config: TradeConfig) -> None:
    if not config.accounts:
        config.accounts.append(TradeAccount())
    account_ids = {account.account_id for account in config.accounts}
    if config.default_account_id not in account_ids:
        config.default_account_id = config.accounts[0].account_id
    TRADE_CONFIG_PATH.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )


class DryRunExecutor(Executor):
    async def execute(self, event: OrderEvent) -> Dict[str, str]:
        return {"status": "dry-run", "event_id": event.event_id}


@dataclass
class AccountRuntime:
    time_offset_ms: int = 0
    last_sync_ms: int = 0
    exchange_info_ms: int = 0
    symbol_filters: Dict[str, Dict[str, float]] = dc_field(default_factory=dict)
    price_cache: Dict[str, Tuple[float, int]] = dc_field(default_factory=dict)
    position_mode: Optional[bool] = None
    position_mode_ms: int = 0
    leverage_cache: Dict[str, Tuple[int, int]] = dc_field(default_factory=dict)
    equity_cache: Tuple[Optional[float], int] = (None, 0)
    balance_cache: Tuple[Optional[Dict[str, float]], int] = (None, 0)
    positions_cache: Tuple[List[Dict[str, Any]], int] = dc_field(default_factory=lambda: ([], 0))


class ApiExecutor(Executor):
    def __init__(self) -> None:
        self._runtime: Dict[str, AccountRuntime] = {}

    def _config_enabled(self, config: TradeConfig) -> bool:
        if config.enabled:
            return True
        return any(account.enabled for account in config.accounts)

    def _load_trade_config(self) -> TradeConfig:
        return load_trade_config()

    def _resolve_account(
        self,
        config: TradeConfig,
        account_id: Optional[str],
    ) -> Optional[TradeAccount]:
        if account_id:
            for account in config.accounts:
                if account.account_id == account_id:
                    return account
        if config.default_account_id:
            for account in config.accounts:
                if account.account_id == config.default_account_id:
                    return account
        return config.accounts[0] if config.accounts else None

    def _get_runtime(self, account_id: str) -> AccountRuntime:
        runtime = self._runtime.get(account_id)
        if not runtime:
            runtime = AccountRuntime()
            self._runtime[account_id] = runtime
        return runtime

    def _sign(self, query: str, secret: str) -> str:
        digest = hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256)
        return digest.hexdigest()

    def _format_qty(self, qty: float) -> str:
        return f"{qty:.8f}".rstrip("0").rstrip(".")

    def _parse_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _quantize_step(self, qty: float, step: float, mode: str) -> float:
        if step <= 0:
            return qty
        ratio = qty / step
        if mode == "ceil":
            ratio = math.ceil(ratio - 1e-12)
        else:
            ratio = math.floor(ratio + 1e-12)
        return round(ratio * step, 8)

    async def _get_exchange_info(
        self,
        account: TradeAccount,
        runtime: AccountRuntime,
    ) -> Dict[str, Dict[str, float]]:
        now = now_ms()
        if runtime.exchange_info_ms and now - runtime.exchange_info_ms < account.exchange_info_ttl_ms:
            return runtime.symbol_filters
        url = f"{account.base_url.rstrip('/')}/fapi/v1/exchangeInfo"
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        if not resp.is_success:
            return runtime.symbol_filters
        data = resp.json()
        filters: Dict[str, Dict[str, float]] = {}
        for symbol_info in data.get("symbols", []) or []:
            symbol = symbol_info.get("symbol")
            if not symbol:
                continue
            entry: Dict[str, float] = {}
            for item in symbol_info.get("filters", []) or []:
                ftype = item.get("filterType")
                if ftype == "LOT_SIZE":
                    entry["step_size"] = float(item.get("stepSize") or 0.0)
                    entry["min_qty"] = float(item.get("minQty") or 0.0)
                elif ftype == "MARKET_LOT_SIZE":
                    entry["market_step_size"] = float(item.get("stepSize") or 0.0)
                    entry["market_min_qty"] = float(item.get("minQty") or 0.0)
                elif ftype == "MIN_NOTIONAL":
                    entry["min_notional"] = float(
                        item.get("notional")
                        or item.get("minNotional")
                        or 0.0
                    )
            filters[symbol] = entry
        runtime.symbol_filters = filters
        runtime.exchange_info_ms = now
        return runtime.symbol_filters

    async def _get_price(
        self,
        account: TradeAccount,
        runtime: AccountRuntime,
        symbol: str,
        source: Optional[str] = None,
    ) -> Optional[float]:
        price_source = (source or account.price_source or "mark").lower()
        now = now_ms()
        cache_key = f"{symbol}|{price_source}"
        cached = runtime.price_cache.get(cache_key)
        if cached and now - cached[1] < account.price_ttl_ms:
            return cached[0]
        timeout = account.timeout_ms / 1000.0
        price = 0.0
        if price_source in {"mark", "index"}:
            url = f"{account.base_url.rstrip('/')}/fapi/v1/premiumIndex?symbol={symbol}"
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
            if resp.is_success:
                data = resp.json()
                field = "markPrice" if price_source == "mark" else "indexPrice"
                price = float(data.get(field) or 0.0)
        if price <= 0:
            url = f"{account.base_url.rstrip('/')}/fapi/v1/ticker/price?symbol={symbol}"
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
            if resp.is_success:
                data = resp.json()
                price = float(data.get("price") or 0.0)
        if price > 0:
            runtime.price_cache[cache_key] = (price, now)
            return price
        return cached[0] if cached else None

    async def _get_position_mode(
        self,
        account: TradeAccount,
        runtime: AccountRuntime,
    ) -> Optional[bool]:
        if not account.auto_position_mode:
            return None
        now = now_ms()
        if runtime.position_mode_ms and now - runtime.position_mode_ms < account.position_mode_ttl_ms:
            return runtime.position_mode
        if not account.api_key or not account.api_secret:
            return None
        await self._sync_time(account, runtime)
        timestamp = now_ms() + runtime.time_offset_ms
        params: Dict[str, Any] = {"timestamp": timestamp}
        if account.recv_window:
            params["recvWindow"] = account.recv_window
        ordered = [(key, params[key]) for key in sorted(params.keys())]
        query = urlencode(ordered, doseq=True)
        signature = self._sign(query, account.api_secret)
        signed_params = ordered + [("signature", signature)]
        url = f"{account.base_url.rstrip('/')}/fapi/v1/positionSide/dual"
        headers = {"X-MBX-APIKEY": account.api_key}
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=signed_params, headers=headers)
        if resp.is_success:
            data = resp.json()
            mode = bool(data.get("dualSidePosition"))
            runtime.position_mode = mode
            runtime.position_mode_ms = now
            return mode
        return runtime.position_mode

    def _clamp_leverage(self, value: float) -> int:
        try:
            leverage = int(round(float(value)))
        except (TypeError, ValueError):
            return 0
        return max(1, min(leverage, 125))

    async def _set_leverage(
        self,
        account: TradeAccount,
        runtime: AccountRuntime,
        symbol: str,
        leverage: float,
    ) -> bool:
        leverage_value = self._clamp_leverage(leverage)
        if leverage_value <= 0:
            return False
        now = now_ms()
        cached = runtime.leverage_cache.get(symbol)
        if cached and cached[0] == leverage_value and now - cached[1] < account.leverage_ttl_ms:
            return True
        if not account.api_key or not account.api_secret:
            return False
        await self._sync_time(account, runtime)
        timestamp = now_ms() + runtime.time_offset_ms
        params: Dict[str, Any] = {
            "symbol": symbol,
            "leverage": leverage_value,
            "timestamp": timestamp,
        }
        if account.recv_window:
            params["recvWindow"] = account.recv_window
        ordered = [(key, params[key]) for key in sorted(params.keys())]
        query = urlencode(ordered, doseq=True)
        signature = self._sign(query, account.api_secret)
        signed_params = ordered + [("signature", signature)]
        url = f"{account.base_url.rstrip('/')}/fapi/v1/leverage"
        headers = {"X-MBX-APIKEY": account.api_key}
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, params=signed_params, headers=headers)
        data = None
        try:
            data = resp.json()
        except ValueError:
            data = resp.text
        if not resp.is_success:
            logger.warning(
                "set leverage failed symbol=%s status=%s response=%s",
                symbol,
                resp.status_code,
                data,
            )
            return False
        if not isinstance(data, dict) or "leverage" not in data:
            logger.warning("set leverage failed symbol=%s response=%s", symbol, data)
            return False
        runtime.leverage_cache[symbol] = (leverage_value, now)
        return True

    async def _adjust_qty(
        self,
        account: TradeAccount,
        runtime: AccountRuntime,
        symbol: str,
        qty: float,
        price_hint: float,
        reduce_only: bool,
        target_notional: Optional[float] = None,
        target_leverage: Optional[float] = None,
        margin_tolerance: Optional[float] = None,
    ) -> Tuple[float, Optional[str]]:
        if not account.auto_adjust_qty:
            return qty, None

        filters = await self._get_exchange_info(account, runtime)
        symbol_filters = filters.get(symbol, {})
        is_market = account.order_type.upper() == "MARKET"
        step_size = symbol_filters.get("market_step_size") if is_market else symbol_filters.get("step_size")
        min_qty = symbol_filters.get("market_min_qty") if is_market else symbol_filters.get("min_qty")
        if not step_size:
            step_size = symbol_filters.get("step_size") or 0.0
        if not min_qty:
            min_qty = symbol_filters.get("min_qty") or 0.0

        bumped_up = False
        if account.min_qty > 0 and qty < account.min_qty:
            qty = account.min_qty
            bumped_up = True
        if account.max_qty > 0 and qty > account.max_qty:
            qty = account.max_qty

        if min_qty > 0 and qty < min_qty:
            qty = min_qty
            bumped_up = True

        min_notional = 0.0 if reduce_only else symbol_filters.get("min_notional") or 0.0
        price = price_hint
        if min_notional > 0:
            if not price or price <= 0:
                price = await self._get_price(account, runtime, symbol) or 0.0
            if price > 0:
                required = min_notional / price
                if qty < required:
                    if account.min_notional_mode == "skip":
                        return 0.0, "below_min_notional"
                    qty = required
                    bumped_up = True

        if step_size and step_size > 0:
            if target_notional and price > 0 and not bumped_up:
                floor_qty = self._quantize_step(qty, step_size, "floor")
                ceil_qty = self._quantize_step(qty, step_size, "ceil")
                floor_notional = abs(floor_qty * price)
                ceil_notional = abs(ceil_qty * price)
                if abs(floor_notional - target_notional) <= abs(ceil_notional - target_notional):
                    qty = floor_qty
                else:
                    qty = ceil_qty
            else:
                mode = "ceil" if bumped_up else "floor"
                qty = self._quantize_step(qty, step_size, mode)

        if min_qty > 0 and qty < min_qty:
            qty = self._quantize_step(min_qty, step_size or 0.0, "ceil")

        if account.max_qty > 0 and qty > account.max_qty:
            qty = self._quantize_step(account.max_qty, step_size or 0.0, "floor")

        tolerance_note = None
        if (
            target_notional
            and target_leverage
            and margin_tolerance
            and margin_tolerance > 0
            and price > 0
            and step_size
            and step_size > 0
        ):
            target_margin = target_notional / target_leverage

            def _margin_error(value: float) -> float:
                return abs((value * price) / target_leverage - target_margin)

            best_qty = qty
            best_err = _margin_error(qty)
            for offset in range(-3, 4):
                if offset == 0:
                    continue
                candidate = qty + (offset * step_size)
                if candidate <= 0:
                    continue
                if min_qty > 0 and candidate < min_qty:
                    continue
                if account.max_qty > 0 and candidate > account.max_qty:
                    continue
                if min_notional > 0 and price and candidate * price < min_notional:
                    continue
                err = _margin_error(candidate)
                if err < best_err:
                    best_err = err
                    best_qty = candidate
            qty = best_qty
            if best_err > margin_tolerance:
                tolerance_note = "margin_tolerance_exceeded"

        if min_notional > 0 and price and qty * price < min_notional:
            return 0.0, "below_min_notional"

        if qty <= 0 or math.isclose(qty, 0.0):
            return 0.0, "zero_qty"

        return qty, tolerance_note

    async def _sync_time(self, account: TradeAccount, runtime: AccountRuntime) -> None:
        if not account.time_sync:
            return
        now = now_ms()
        if now - runtime.last_sync_ms < account.time_sync_interval_ms:
            return
        url = f"{account.base_url.rstrip('/')}/fapi/v1/time"
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        if resp.is_success:
            data = resp.json()
            server_time = int(data.get("serverTime") or 0)
            if server_time:
                runtime.time_offset_ms = server_time - now
                runtime.last_sync_ms = now

    async def get_follower_equity(self, account_id: Optional[str] = None) -> Optional[float]:
        balance = await self.get_follower_balance(account_id)
        if balance:
            value = (
                balance.get("margin_balance")
                or balance.get("available_balance")
                or balance.get("wallet_balance")
            )
            if value:
                return value
        config = self._load_trade_config()
        if not self._config_enabled(config):
            return None
        account = self._resolve_account(config, account_id)
        if not account or not account.enabled:
            return None
        if not account.api_key or not account.api_secret:
            return None
        runtime = self._get_runtime(account.account_id)
        now = now_ms()
        cached_value, cached_ms = runtime.equity_cache
        if cached_value is not None and now - cached_ms < 2000:
            return cached_value
        await self._sync_time(account, runtime)
        timestamp = now_ms() + runtime.time_offset_ms
        params: Dict[str, Any] = {"timestamp": timestamp}
        if account.recv_window:
            params["recvWindow"] = account.recv_window
        ordered = [(key, params[key]) for key in sorted(params.keys())]
        query = urlencode(ordered, doseq=True)
        signature = self._sign(query, account.api_secret)
        signed_params = ordered + [("signature", signature)]
        url = f"{account.base_url.rstrip('/')}/fapi/v2/account"
        headers = {"X-MBX-APIKEY": account.api_key}
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=signed_params, headers=headers)
        if not resp.is_success:
            return None
        data = resp.json()
        raw_value = data.get("availableBalance") or data.get("totalWalletBalance")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if value > 0:
            runtime.equity_cache = (value, now)
        return value

    async def get_follower_balance(
        self,
        account_id: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        config = self._load_trade_config()
        if not self._config_enabled(config):
            return None
        account = self._resolve_account(config, account_id)
        if not account or not account.enabled:
            return None
        if not account.api_key or not account.api_secret:
            return None
        runtime = self._get_runtime(account.account_id)
        now = now_ms()
        cached_value, cached_ms = runtime.balance_cache
        if cached_value is not None and now - cached_ms < 2000:
            return cached_value
        await self._sync_time(account, runtime)
        timestamp = now_ms() + runtime.time_offset_ms
        params: Dict[str, Any] = {"timestamp": timestamp}
        if account.recv_window:
            params["recvWindow"] = account.recv_window
        ordered = [(key, params[key]) for key in sorted(params.keys())]
        query = urlencode(ordered, doseq=True)
        signature = self._sign(query, account.api_secret)
        signed_params = ordered + [("signature", signature)]
        url = f"{account.base_url.rstrip('/')}/fapi/v2/account"
        headers = {"X-MBX-APIKEY": account.api_key}
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=signed_params, headers=headers)
        if not resp.is_success:
            return cached_value
        data = resp.json()
        balance = {
            "wallet_balance": self._parse_float(data.get("totalWalletBalance")),
            "available_balance": self._parse_float(data.get("availableBalance")),
            "margin_balance": self._parse_float(data.get("totalMarginBalance")),
            "unrealized_pnl": self._parse_float(data.get("totalUnrealizedProfit")),
            "initial_margin": self._parse_float(data.get("totalInitialMargin")),
            "maint_margin": self._parse_float(data.get("totalMaintMargin")),
        }
        runtime.balance_cache = (balance, now)
        preferred = balance["margin_balance"] or balance["available_balance"] or balance["wallet_balance"]
        if preferred > 0:
            runtime.equity_cache = (preferred, now)
        return balance

    async def get_follower_positions(
        self,
        account_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        config = self._load_trade_config()
        if not self._config_enabled(config):
            return []
        account = self._resolve_account(config, account_id)
        if not account or not account.enabled:
            return []
        if not account.api_key or not account.api_secret:
            return []
        runtime = self._get_runtime(account.account_id)
        now = now_ms()
        cached_items, cached_ms = runtime.positions_cache
        if cached_items and now - cached_ms < 2000:
            return cached_items
        await self._sync_time(account, runtime)
        timestamp = now_ms() + runtime.time_offset_ms
        params: Dict[str, Any] = {"timestamp": timestamp}
        if account.recv_window:
            params["recvWindow"] = account.recv_window
        ordered = [(key, params[key]) for key in sorted(params.keys())]
        query = urlencode(ordered, doseq=True)
        signature = self._sign(query, account.api_secret)
        signed_params = ordered + [("signature", signature)]
        url = f"{account.base_url.rstrip('/')}/fapi/v2/positionRisk"
        headers = {"X-MBX-APIKEY": account.api_key}
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=signed_params, headers=headers)
        if not resp.is_success:
            return cached_items
        data = resp.json()
        if not isinstance(data, list):
            return cached_items
        filtered: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                amt = float(item.get("positionAmt") or 0.0)
            except (TypeError, ValueError):
                amt = 0.0
            if abs(amt) <= 0:
                continue
            filtered.append(item)
        runtime.positions_cache = (filtered, now)
        return filtered

    async def _resolve_reduce_position(
        self,
        account: TradeAccount,
        runtime: AccountRuntime,
        symbol: str,
        position_side: Optional[str],
        side: Optional[str],
        reduce_only: bool,
    ) -> Tuple[Optional[float], Optional[str]]:
        items = await self.get_follower_positions(account.account_id)
        if not items:
            return None, None
        symbol_items = [item for item in items if str(item.get("symbol") or "") == symbol]
        if not symbol_items:
            return None, None

        def _amt(item: Dict[str, Any]) -> float:
            try:
                return float(item.get("positionAmt") or 0.0)
            except (TypeError, ValueError):
                return 0.0

        def _pos_side(item: Dict[str, Any]) -> str:
            value = str(item.get("positionSide") or "").upper()
            if value == "BOTH":
                value = "LONG" if _amt(item) > 0 else "SHORT"
            return value if value in {"LONG", "SHORT"} else ""

        wanted = (position_side or "").upper()
        if wanted and wanted != "BOTH":
            for item in symbol_items:
                if _pos_side(item) == wanted:
                    amt = _amt(item)
                    if amt:
                        return amt, wanted

        positions: Dict[str, float] = {}
        for item in symbol_items:
            pos_side = _pos_side(item)
            if not pos_side:
                continue
            amt = _amt(item)
            if amt:
                positions[pos_side] = amt
        if not positions:
            return None, None
        if len(positions) == 1:
            pos_side, amt = next(iter(positions.items()))
            return amt, pos_side

        side = (side or "").upper()
        inferred = ""
        if reduce_only:
            if side == "SELL":
                inferred = "LONG"
            elif side == "BUY":
                inferred = "SHORT"
        else:
            if side == "BUY":
                inferred = "LONG"
            elif side == "SELL":
                inferred = "SHORT"
        if inferred and inferred in positions:
            return positions[inferred], inferred
        return None, None

    async def execute(self, event: OrderEvent) -> Dict[str, str]:
        config = self._load_trade_config()
        if not self._config_enabled(config):
            return {"status": "disabled", "event_id": event.event_id}
        account = self._resolve_account(config, event.trade_account_id)
        if not account:
            return {"status": "error", "event_id": event.event_id, "note": "account_not_found"}
        if not account.enabled:
            return {"status": "disabled", "event_id": event.event_id, "note": "account_disabled"}
        if not account.api_key or not account.api_secret:
            return {"status": "error", "event_id": event.event_id, "note": "missing api key/secret"}
        runtime = self._get_runtime(account.account_id)

        if event.action in {"reduce", "close"}:
            event.reduce_only = True

        qty = abs(event.follower_qty)
        price_for_adjust = event.avg_price
        if event.reduce_only and event.action in {"reduce", "close"}:
            position_amt, inferred_side = await self._resolve_reduce_position(
                account,
                runtime,
                event.symbol,
                event.position_side,
                event.side,
                event.reduce_only,
            )
            if position_amt is None:
                return {"status": "skipped", "event_id": event.event_id, "note": "no_position"}
            event.side = "SELL" if position_amt > 0 else "BUY"
            if inferred_side:
                event.position_side = inferred_side
            if event.action == "close":
                qty = abs(position_amt)
            else:
                desired = abs(event.follower_qty) if abs(event.follower_qty) > 0 else abs(position_amt)
                qty = min(desired, abs(position_amt))
            event.follower_qty = -qty if event.side == "SELL" else qty
        target_notional = None
        if account.usdt_order_mode and not event.reduce_only and event.action in {"open", "add"}:
            notional = event.follower_notional
            if notional is None or notional <= 0:
                notional = abs(event.follower_qty) * max(event.avg_price, 0.0)
            if notional <= 0:
                return {
                    "status": "error",
                    "event_id": event.event_id,
                    "note": "notional_unavailable",
                }
            price = await self._get_price(account, runtime, event.symbol) or 0.0
            if price <= 0:
                return {
                    "status": "error",
                    "event_id": event.event_id,
                    "note": "price_unavailable",
                }
            qty = notional / price
            price_for_adjust = price
            target_notional = notional
        if qty <= 0 or math.isclose(qty, 0.0):
            return {"status": "skipped", "event_id": event.event_id, "note": "zero qty"}

        adjusted_qty, adjust_note = await self._adjust_qty(
            account,
            runtime,
            event.symbol,
            qty,
            price_for_adjust,
            event.reduce_only,
            target_notional=target_notional,
            target_leverage=event.follower_leverage,
            margin_tolerance=MARGIN_TOLERANCE_USDT,
        )
        if adjusted_qty <= 0:
            return {
                "status": "skipped",
                "event_id": event.event_id,
                "note": adjust_note or "qty_adjusted_to_zero",
            }
        if event.follower_qty < 0:
            event.follower_qty = -adjusted_qty
        else:
            event.follower_qty = adjusted_qty

        if account.auto_set_leverage and event.follower_leverage:
            ok = await self._set_leverage(
                account,
                runtime,
                event.symbol,
                event.follower_leverage,
            )
            if not ok:
                return {
                    "status": "error",
                    "event_id": event.event_id,
                    "note": "leverage_set_failed",
                }

        await self._sync_time(account, runtime)
        timestamp = now_ms() + runtime.time_offset_ms
        send_position_side = account.send_position_side
        position_mode = await self._get_position_mode(account, runtime)
        if position_mode is not None:
            send_position_side = position_mode
        if send_position_side and event.position_side:
            if event.position_side.upper() == "BOTH":
                event.position_side = "LONG" if event.side == "BUY" else "SHORT"
        params: Dict[str, Any] = {
            "symbol": event.symbol,
            "side": event.side,
            "type": account.order_type,
            "quantity": self._format_qty(adjusted_qty),
            "timestamp": timestamp,
        }
        if send_position_side and event.position_side:
            params["positionSide"] = event.position_side
        if event.reduce_only:
            params["reduceOnly"] = "true"
        if account.recv_window:
            params["recvWindow"] = account.recv_window

        ordered = [(key, params[key]) for key in sorted(params.keys())]
        query = urlencode(ordered, doseq=True)
        signature = self._sign(query, account.api_secret)
        url = f"{account.base_url.rstrip('/')}/fapi/v1/order"
        headers = {"X-MBX-APIKEY": account.api_key}
        signed_params = ordered + [("signature", signature)]
        timeout = account.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, params=signed_params, headers=headers)
        executed_at = now_ms()
        event.executed_at = executed_at
        binance_time = event.order_update_time or event.order_time
        if binance_time and binance_time > 0:
            event.latency_ms = executed_at - binance_time
        response = resp.json()
        logger.info(
            "order executed symbol=%s side=%s qty=%.8f latency=%dms event_id=%s",
            event.symbol,
            event.side,
            abs(event.follower_qty),
            event.latency_ms or 0,
            event.event_id,
        )
        return {"status": "sent", "event_id": event.event_id, "response": json.dumps(response)}

"""OKX trade executor using official API"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from ..core.logging import get_logger
from ..core.paths import OKX_TRADE_CONFIG_PATH, TRADE_CONFIG_PATH
from ..core.storage import load_json
from ..core.time import now_ms
from ..domain.events import OrderEvent
from ..domain.okx_trade import OKXTradeAccount, OKXTradeConfig
from ..domain.trade import TradeConfig

logger = get_logger()


def _resolve_okx_base_url(value: str) -> str:
    if value and "binance" not in value:
        return value
    return "https://www.okx.com"


def _build_okx_accounts_from_trade_config(trade_config: TradeConfig) -> List[OKXTradeAccount]:
    accounts: List[OKXTradeAccount] = []
    for account in trade_config.accounts:
        if account.exchange != "okx":
            continue
        accounts.append(
            OKXTradeAccount(
                account_id=account.account_id or "default",
                name=account.name or account.account_id or "OKX",
                enabled=account.enabled,
                base_url=_resolve_okx_base_url(account.base_url),
                api_key=account.api_key,
                api_secret=account.api_secret,
                passphrase=getattr(account, "passphrase", ""),
                simulated=getattr(account, "simulated", False),
                timeout_ms=account.timeout_ms,
                auto_set_leverage=account.auto_set_leverage,
                leverage_ttl_ms=account.leverage_ttl_ms,
            )
        )
    return accounts


def load_okx_trade_config() -> OKXTradeConfig:
    if OKX_TRADE_CONFIG_PATH.exists():
        try:
            data = json.loads(OKX_TRADE_CONFIG_PATH.read_text(encoding="utf-8-sig"))
            config = OKXTradeConfig.model_validate(data)
        except Exception as exc:
            logger.warning("okx_trade_config.json invalid error=%s", exc)
        else:
            if config.accounts:
                return config

    trade_config = load_json(TRADE_CONFIG_PATH, TradeConfig, TradeConfig())
    accounts = _build_okx_accounts_from_trade_config(trade_config)
    if not accounts:
        return OKXTradeConfig(accounts=[OKXTradeAccount()])

    default_id = trade_config.default_account_id or accounts[0].account_id
    if default_id not in {account.account_id for account in accounts}:
        default_id = accounts[0].account_id
    enabled = any(account.enabled for account in accounts)
    return OKXTradeConfig(
        enabled=enabled,
        default_account_id=default_id,
        accounts=accounts,
    )


def save_okx_trade_config(config: OKXTradeConfig) -> None:
    if not config.accounts:
        config.accounts.append(OKXTradeAccount())
    OKX_TRADE_CONFIG_PATH.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


@dataclass
class OKXAccountRuntime:
    leverage_cache: Dict[str, Tuple[int, int]] = dc_field(default_factory=dict)
    equity_cache: Tuple[Optional[float], int] = (None, 0)
    balance_cache: Tuple[Optional[Dict[str, float]], int] = (None, 0)
    positions_cache: Tuple[List[Dict[str, Any]], int] = dc_field(default_factory=lambda: ([], 0))
    inst_info_cache: Dict[str, Dict[str, Any]] = dc_field(default_factory=dict)
    inst_info_ms: int = 0


_OKX_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_OKX_DEFAULT_LIMITS = httpx.Limits(max_keepalive_connections=20, max_connections=50)
_OKX_INSTRUMENT_TTL_MS = 60 * 60 * 1000  # 1h cache for instrument metadata


class OKXExecutor:
    """OKX交易执行器"""

    def __init__(self) -> None:
        self._runtime: Dict[str, OKXAccountRuntime] = {}
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=_OKX_DEFAULT_TIMEOUT,
            limits=_OKX_DEFAULT_LIMITS,
        )
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._config_cache: Optional[Tuple[OKXTradeConfig, float]] = None

    def _get_client(self, account: OKXTradeAccount) -> httpx.AsyncClient:
        base = (account.base_url or "").rstrip("/")
        if not base:
            return self._client
        existing = self._clients.get(base)
        if existing is not None:
            return existing
        client = httpx.AsyncClient(timeout=_OKX_DEFAULT_TIMEOUT, limits=_OKX_DEFAULT_LIMITS)
        self._clients[base] = client
        return client

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            pass
        for client in list(self._clients.values()):
            try:
                await client.aclose()
            except Exception:
                pass
        self._clients.clear()

    async def _get_instrument(
        self,
        account: OKXTradeAccount,
        inst_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch (and cache 1h) SWAP instrument metadata: ctVal/lotSz/minSz/tickSz."""
        runtime = self._get_runtime(account.account_id)
        cached = runtime.inst_info_cache.get(inst_id)
        if cached and (now_ms() - runtime.inst_info_ms) < _OKX_INSTRUMENT_TTL_MS:
            return cached
        path = "/api/v5/public/instruments"
        params = {"instType": "SWAP", "instId": inst_id}
        url = f"{account.base_url.rstrip('/')}{path}"
        timeout = account.timeout_ms / 1000.0
        try:
            client = self._get_client(account)
            resp = await client.get(url, params=params, timeout=timeout)
            data = resp.json()
        except Exception as exc:
            logger.warning("okx instrument fetch failed inst_id=%s err=%s", inst_id, exc)
            return cached
        if not isinstance(data, dict) or data.get("code") != "0":
            return cached
        items = data.get("data") or []
        if not items:
            return cached
        info = items[0]
        runtime.inst_info_cache[inst_id] = info
        runtime.inst_info_ms = now_ms()
        return info

    @staticmethod
    def _quantize_lot(value: float, lot: float, mode: str = "floor") -> float:
        if lot <= 0:
            return value
        ratio = value / lot
        if mode == "ceil":
            ratio = math.ceil(ratio - 1e-12)
        else:
            ratio = math.floor(ratio + 1e-12)
        return ratio * lot

    def _config_enabled(self, config: OKXTradeConfig) -> bool:
        if config.enabled:
            return True
        return any(account.enabled for account in config.accounts)

    def _load_config(self) -> OKXTradeConfig:
        return load_okx_trade_config()

    def has_account(self, account_id: str) -> bool:
        if not account_id:
            return False
        config = self._load_config()
        return any(account.account_id == account_id for account in config.accounts)

    def _require_account(self, account_id: Optional[str]) -> OKXTradeAccount:
        config = self._load_config()
        if not self._config_enabled(config):
            raise ValueError("okx_disabled")
        account = self._resolve_account(config, account_id)
        if not account or not account.enabled:
            raise ValueError("account_disabled")
        if not account.api_key or not account.api_secret or not account.passphrase:
            raise ValueError("missing_credentials")
        return account


    def _resolve_account(
        self,
        config: OKXTradeConfig,
        account_id: Optional[str],
    ) -> Optional[OKXTradeAccount]:
        if account_id:
            for account in config.accounts:
                if account.account_id == account_id:
                    return account
        if config.default_account_id:
            for account in config.accounts:
                if account.account_id == config.default_account_id:
                    return account
        return config.accounts[0] if config.accounts else None

    def _get_runtime(self, account_id: str) -> OKXAccountRuntime:
        runtime = self._runtime.get(account_id)
        if not runtime:
            runtime = OKXAccountRuntime()
            self._runtime[account_id] = runtime
        return runtime

    def _get_timestamp(self) -> str:
        """获取ISO 8601格式时间戳"""
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    def _sign(self, timestamp: str, method: str, path: str, body: str, secret: str) -> str:
        """
        OKX签名: base64(hmac-sha256(timestamp + method + path + body))
        """
        message = timestamp + method.upper() + path + (body or "")
        mac = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _build_headers(self, account: OKXTradeAccount, timestamp: str, method: str, path: str, body: str = "") -> Dict[str, str]:
        """构建请求头"""
        signature = self._sign(timestamp, method, path, body, account.api_secret)
        headers = {
            "OK-ACCESS-KEY": account.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": account.passphrase,
            "Content-Type": "application/json",
        }
        if account.simulated:
            headers["x-simulated-trading"] = "1"
        return headers

    async def _request(
        self,
        account: OKXTradeAccount,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        query = ""
        if params:
            ordered = [(key, params[key]) for key in sorted(params.keys()) if params[key] not in ("", None)]
            query = urlencode(ordered, doseq=True)
        path_with_query = f"{path}?{query}" if query else path
        body_str = json.dumps(body) if body else ""
        timestamp = self._get_timestamp()
        headers = self._build_headers(account, timestamp, method, path_with_query, body_str)
        url = f"{account.base_url.rstrip('/')}{path_with_query}"
        timeout = account.timeout_ms / 1000.0

        client = self._get_client(account)
        if method.upper() == "GET":
            resp = await client.get(url, headers=headers, timeout=timeout)
        else:
            resp = await client.post(url, headers=headers, content=body_str, timeout=timeout)
        return resp.json()


    @staticmethod
    def _binance_to_okx_symbol(symbol: str) -> str:
        """Binance符号转OKX符号: BTCUSDT -> BTC-USDT-SWAP"""
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}-USDT-SWAP"
        return symbol

    @staticmethod
    def _okx_to_binance_symbol(inst_id: str) -> str:
        """OKX符号转Binance符号: BTC-USDT-SWAP -> BTCUSDT"""
        parts = inst_id.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}{parts[1]}"
        return inst_id

    async def _set_leverage(
        self,
        account: OKXTradeAccount,
        runtime: OKXAccountRuntime,
        inst_id: str,
        leverage: int,
        pos_side: str,
        mgn_mode: str = "cross",
    ) -> bool:
        """设置杠杆倍数"""
        now = now_ms()
        cache_key = f"{inst_id}|{pos_side}"
        cached = runtime.leverage_cache.get(cache_key)
        if cached and cached[0] == leverage and now - cached[1] < account.leverage_ttl_ms:
            return True

        timestamp = self._get_timestamp()
        path = "/api/v5/account/set-leverage"

        body_dict: Dict[str, Any] = {
            "instId": inst_id,
            "lever": str(leverage),
            "mgnMode": mgn_mode,
        }
        if mgn_mode == "isolated":
            body_dict["posSide"] = pos_side.lower()

        body = json.dumps(body_dict)
        headers = self._build_headers(account, timestamp, "POST", path, body)
        url = f"{account.base_url.rstrip('/')}{path}"
        timeout = account.timeout_ms / 1000.0

        try:
            client = self._get_client(account)
            resp = await client.post(url, headers=headers, content=body, timeout=timeout)
            data = resp.json()

            if data.get("code") == "0":
                runtime.leverage_cache[cache_key] = (leverage, now)
                return True
            else:
                logger.warning("OKX set leverage failed: %s", data.get("msg"))
                return False
        except Exception as e:
            logger.error("OKX set leverage error: %s", e)
            return False

    async def get_follower_balance(
        self,
        account_id: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        config = self._load_config()
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

        def _float(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        timestamp = self._get_timestamp()
        path = "/api/v5/account/balance"
        headers = self._build_headers(account, timestamp, "GET", path)
        url = f"{account.base_url.rstrip('/')}{path}"
        timeout = account.timeout_ms / 1000.0

        try:
            client = self._get_client(account)
            resp = await client.get(url, headers=headers, timeout=timeout)
            data = resp.json()

            if data.get("code") != "0":
                return cached_value

            payload = (data.get("data") or [{}])[0]
            details = payload.get("details") or []
            usdt = None
            for item in details:
                if item.get("ccy") == "USDT":
                    usdt = item
                    break

            total_eq = _float(payload.get("totalEq"))
            wallet_balance = _float(usdt.get("cashBal") if usdt else 0) or _float(usdt.get("eq") if usdt else 0) or total_eq
            available_balance = _float(usdt.get("availBal") if usdt else 0) or _float(usdt.get("availEq") if usdt else 0)
            margin_balance = _float(usdt.get("eq") if usdt else 0) or total_eq

            balance = {
                "wallet_balance": wallet_balance,
                "available_balance": available_balance,
                "margin_balance": margin_balance,
                "unrealized_pnl": _float(usdt.get("upl") if usdt else 0),
                "initial_margin": _float(usdt.get("imr") if usdt else 0),
                "maint_margin": _float(usdt.get("mmr") if usdt else 0),
            }
            runtime.balance_cache = (balance, now)
            preferred = balance["margin_balance"] or balance["available_balance"] or balance["wallet_balance"]
            if preferred > 0:
                runtime.equity_cache = (preferred, now)
            return balance
        except Exception as e:
            logger.error("OKX get balance error: %s", e)
            return cached_value

    async def get_follower_equity(self, account_id: Optional[str] = None) -> Optional[float]:
        """获取跟随者账户权益"""
        balance = await self.get_follower_balance(account_id)
        if balance:
            value = (
                balance.get("margin_balance")
                or balance.get("available_balance")
                or balance.get("wallet_balance")
            )
            if value:
                return value
        return None

    async def get_follower_positions(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取跟随者持仓"""
        config = self._load_config()
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

        timestamp = self._get_timestamp()
        path = "/api/v5/account/positions?instType=SWAP"
        headers = self._build_headers(account, timestamp, "GET", path)
        url = f"{account.base_url.rstrip('/')}{path}"
        timeout = account.timeout_ms / 1000.0

        try:
            client = self._get_client(account)
            resp = await client.get(url, headers=headers, timeout=timeout)
            data = resp.json()

            if data.get("code") == "0":
                positions = []
                for item in data.get("data", []):
                    pos = float(item.get("pos", 0))
                    if abs(pos) > 0:
                        positions.append({
                            "symbol": self._okx_to_binance_symbol(item.get("instId", "")),
                            "instId": item.get("instId"),
                            "positionSide": "LONG" if pos > 0 else "SHORT",
                            "positionAmt": pos,
                            "entryPrice": float(item.get("avgPx", 0)),
                            "markPrice": float(item.get("markPx", 0)),
                            "leverage": int(item.get("lever", 1)),
                            "unrealizedProfit": float(item.get("upl", 0)),
                        })
                runtime.positions_cache = (positions, now)
                return positions
            return cached_items
        except Exception as e:
            logger.error("OKX get positions error: %s", e)
            return cached_items

    async def get_existing_leading_positions(
        self,
        account_id: Optional[str] = None,
        inst_id: str = "",
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "GET",
            "/api/v5/copytrading/current-subpositions",
            params={"instId": inst_id},
        )

    async def get_leading_position_history(
        self,
        account_id: Optional[str] = None,
        inst_id: str = "",
        after: str = "",
        before: str = "",
        limit: str = "",
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "GET",
            "/api/v5/copytrading/subpositions-history",
            params={
                "instId": inst_id,
                "after": after,
                "before": before,
                "limit": limit,
            },
        )

    async def place_leading_stop_order(
        self,
        account_id: Optional[str] = None,
        sub_pos_id: str = "",
        tp_trigger_px: str = "",
        sl_trigger_px: str = "",
        tp_trigger_px_type: str = "",
        sl_trigger_px_type: str = "",
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "POST",
            "/api/v5/copytrading/algo-order",
            body={
                "subPosId": sub_pos_id,
                "tpTriggerPx": tp_trigger_px,
                "slTriggerPx": sl_trigger_px,
                "tpTriggerPxType": tp_trigger_px_type,
                "slTriggerPxType": sl_trigger_px_type,
            },
        )

    async def close_leading_position(
        self,
        account_id: Optional[str] = None,
        sub_pos_id: str = "",
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "POST",
            "/api/v5/copytrading/close-subposition",
            body={"subPosId": sub_pos_id},
        )

    async def get_leading_instruments(
        self,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(account, "GET", "/api/v5/copytrading/instruments")

    async def amend_leading_instruments(
        self,
        account_id: Optional[str] = None,
        inst_id: str = "",
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "POST",
            "/api/v5/copytrading/set-instruments",
            body={"instId": inst_id},
        )

    async def get_profit_sharing_details(
        self,
        account_id: Optional[str] = None,
        after: str = "",
        before: str = "",
        limit: str = "",
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "GET",
            "/api/v5/copytrading/profit-sharing-details",
            params={"after": after, "before": before, "limit": limit},
        )

    async def get_total_profit_sharing(
        self,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "GET",
            "/api/v5/copytrading/total-profit-sharing",
        )

    async def get_unrealized_profit_sharing_details(
        self,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        account = self._require_account(account_id)
        return await self._request(
            account,
            "GET",
            "/api/v5/copytrading/unrealized-profit-sharing-details",
        )

    async def execute(self, event: OrderEvent) -> Dict[str, str]:
        """执行跟单订单"""
        config = self._load_config()
        if not self._config_enabled(config):
            return {"status": "disabled", "event_id": event.event_id}

        account = self._resolve_account(config, event.trade_account_id)
        if not account:
            return {"status": "error", "event_id": event.event_id, "note": "account_not_found"}
        if not account.enabled:
            return {"status": "disabled", "event_id": event.event_id, "note": "account_disabled"}
        if not account.api_key or not account.api_secret or not account.passphrase:
            return {"status": "error", "event_id": event.event_id, "note": "missing credentials"}

        runtime = self._get_runtime(account.account_id)

        # 转换符号
        inst_id = self._binance_to_okx_symbol(event.symbol)

        # 确定方向
        side = event.side.lower()  # buy/sell
        pos_side = event.position_side.lower() if event.position_side else "net"  # long/short/net

        # 设置杠杆
        if account.auto_set_leverage and event.follower_leverage:
            leverage = max(1, min(int(event.follower_leverage), 125))
            await self._set_leverage(account, runtime, inst_id, leverage, pos_side)

        # 构建订单
        coin_qty = abs(event.follower_qty)
        if coin_qty <= 0:
            return {"status": "skipped", "event_id": event.event_id, "note": "zero_qty"}

        # OKX SWAP `sz` is in CONTRACTS, not coins. Convert via ctVal and quantize by lotSz.
        contracts = coin_qty
        instrument = await self._get_instrument(account, inst_id)
        if instrument:
            try:
                ct_val = float(instrument.get("ctVal") or 0)
                lot_sz = float(instrument.get("lotSz") or 0)
                min_sz = float(instrument.get("minSz") or 0)
            except (TypeError, ValueError):
                ct_val = lot_sz = min_sz = 0.0
            if ct_val > 0:
                # Reduce: ceil so the dust closes; open: floor to avoid over-sizing.
                quantize_mode = "ceil" if event.reduce_only else "floor"
                contracts = self._quantize_lot(coin_qty / ct_val, lot_sz, quantize_mode)
                if min_sz > 0 and contracts < min_sz:
                    if event.reduce_only:
                        contracts = min_sz
                    else:
                        return {
                            "status": "skipped",
                            "event_id": event.event_id,
                            "note": "below_min_sz",
                        }
        else:
            logger.warning(
                "okx instrument metadata missing inst_id=%s; sending raw coin qty (may be wrong unit)",
                inst_id,
            )

        if contracts <= 0:
            return {"status": "skipped", "event_id": event.event_id, "note": "zero_contracts"}

        timestamp = self._get_timestamp()
        path = "/api/v5/trade/order"

        body_dict: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cross",  # 全仓模式
            "side": side,
            "ordType": "market",
            "sz": str(contracts),
        }

        # 双向持仓模式
        hedge_pos_side = pos_side in ("long", "short")
        if hedge_pos_side:
            body_dict["posSide"] = pos_side

        # OKX rule: reduceOnly is only valid in NET (one-way) mode. In hedge mode
        # (posSide=long/short) the side+posSide already implies reduce semantics
        # and reduceOnly will be rejected with code 51000/51020.
        if event.reduce_only and not hedge_pos_side:
            body_dict["reduceOnly"] = True

        body = json.dumps(body_dict)
        headers = self._build_headers(account, timestamp, "POST", path, body)
        url = f"{account.base_url.rstrip('/')}{path}"
        timeout = account.timeout_ms / 1000.0

        try:
            client = self._get_client(account)
            resp = await client.post(url, headers=headers, content=body, timeout=timeout)

            executed_at = now_ms()
            event.executed_at = executed_at
            if event.order_update_time and event.order_update_time > 0:
                event.latency_ms = executed_at - event.order_update_time

            data = resp.json()
            logger.info(
                "OKX order executed instId=%s side=%s coin_qty=%.8f contracts=%.8f latency=%dms event_id=%s",
                inst_id,
                side,
                coin_qty,
                contracts,
                event.latency_ms or 0,
                event.event_id,
            )

            if data.get("code") == "0":
                order_data = data.get("data", [{}])[0]
                return {
                    "status": "sent",
                    "event_id": event.event_id,
                    "order_id": order_data.get("ordId", ""),
                    "response": json.dumps(data),
                }
            else:
                return {
                    "status": "error",
                    "event_id": event.event_id,
                    "note": data.get("msg", "unknown error"),
                    "response": json.dumps(data),
                }
        except Exception as e:
            logger.error("OKX execute error: %s", e)
            return {"status": "error", "event_id": event.event_id, "note": str(e)}

"""OKX public copy trading API session"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class OKXSession:
    """OKX公开跟单API会话 - 无需认证"""

    def __init__(
        self,
        api_base: str = "https://www.okx.com",
        request_timeout_ms: int = 10000,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.request_timeout_ms = request_timeout_ms
        self.connected = True  # 公开API，始终"已连接"
        self.last_error: Optional[str] = None
        self.time_offset_ms = 0

    async def connect(self) -> bool:
        """公开API无需连接"""
        self.connected = True
        return True

    async def close(self) -> None:
        """关闭会话"""
        self.connected = False

    async def fetch_positions(self, unique_code: str) -> Dict[str, Any]:
        """
        获取交易员当前持仓 (公开API)

        API: GET /api/v5/copytrading/public-current-subpositions
        参数: instType=SWAP, uniqueCode={交易员ID}
        """
        url = f"{self.api_base}/api/v5/copytrading/public-current-subpositions"
        params = {"instType": "SWAP", "uniqueCode": unique_code}
        timeout = self.request_timeout_ms / 1000.0

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
                data = resp.json()

            # 转换为统一格式
            if data.get("code") == "0":
                positions = self._parse_positions(data.get("data", []))
                return {
                    "success": True,
                    "positions": positions,
                    "data": positions,
                    "empty_confirmed": len(positions) == 0,
                    "raw": data,
                }
            else:
                self.last_error = data.get("msg", "Unknown error")
                return {
                    "success": False,
                    "error": self.last_error,
                    "positions": [],
                    "data": [],
                    "empty_confirmed": True,
                    "raw": data,
                }
        except Exception as e:
            self.last_error = str(e)
            return {
                "success": False,
                "error": self.last_error,
                "positions": [],
                "data": [],
                "empty_confirmed": True,
            }

    def _parse_positions(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        解析OKX持仓数据为统一格式

        OKX格式:
        - instId: BTC-USDT-SWAP
        - subPos: 持仓量 (正数多头，负数空头)
        - openAvgPx: 开仓均价
        - markPx: 标记价格
        - lever: 杠杆倍数
        - upl: 未实现盈亏
        - margin: 保证金

        统一格式 (兼容Binance):
        - symbol: BTCUSDT
        - positionSide: LONG/SHORT
        - positionAmt: 持仓量 (带符号)
        - positionAmount: 持仓量绝对值
        - entryPrice: 开仓均价
        - markPrice: 标记价格
        - leverage: 杠杆倍数
        - unrealizedProfit: 未实现盈亏
        - margin: 保证金
        """
        positions = []
        for item in data:
            inst_id = item.get("instId", "")
            try:
                sub_pos = float(item.get("subPos", 0))
            except (TypeError, ValueError):
                sub_pos = 0.0

            if sub_pos == 0:
                continue

            # Prefer the upstream `posSide` (long/short) when present — more
            # reliable than inferring from the sign of subPos, since OKX
            # net-mode and isolated-margin can return signed quantities with
            # an explicit posSide that disagrees with the sign convention.
            raw_side = (item.get("posSide") or "").lower()
            if raw_side == "long":
                position_side = "LONG"
            elif raw_side == "short":
                position_side = "SHORT"
            else:
                position_side = "LONG" if sub_pos > 0 else "SHORT"
            # `side` mirrors the Binance schema (BUY/SELL) so downstream
            # event-generator and notifier templates can read either field
            # without an OKX-specific branch.
            side = "BUY" if position_side == "LONG" else "SELL"

            symbol = self._okx_to_binance_symbol(inst_id)

            positions.append({
                "symbol": symbol,
                "instId": inst_id,
                "side": side,
                "positionSide": position_side,
                "positionAmt": sub_pos,
                "positionAmount": abs(sub_pos),
                "entryPrice": float(item.get("openAvgPx", 0)),
                "markPrice": float(item.get("markPx", 0)),
                "leverage": int(item.get("lever", 1)),
                "unrealizedProfit": float(item.get("upl", 0)),
                "uplRatio": float(item.get("uplRatio", 0)),
                "margin": float(item.get("margin", 0)),
                "mgnMode": item.get("mgnMode", "cross"),
                "subPosId": item.get("subPosId", ""),
                "openTime": int(item.get("openTime", 0) or 0),
            })

        return positions

    async def fetch_detail(self, unique_code: str) -> Dict[str, Any]:
        """Resolve a single lead trader's stats by uniqueCode.

        OKX's `/public-lead-traders` endpoint ignores the `uniqueCode`
        query param and always returns the full leaderboard, so we scan the
        leaderboard ranks client-side. Field names follow what OKX actually
        ships today: `nickName`, `aum`, `pnlRatio`, `copyTraderNum`,
        `accCopyTraderNum`, `leadDays`, `winRatio` (when available).
        """
        url = f"{self.api_base}/api/v5/copytrading/public-lead-traders"
        params = {"instType": "SWAP", "sortType": "overview"}
        timeout = self.request_timeout_ms / 1000.0

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
                payload = resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

        if payload.get("code") != "0":
            return {"success": False, "error": payload.get("msg", "Unknown error")}

        ranks = (((payload.get("data") or [{}])[0]).get("ranks") or [])
        target = next(
            (r for r in ranks if (r.get("uniqueCode") or "").upper() == unique_code.upper()),
            None,
        )
        if target is None:
            return {
                "success": False,
                "error": "Trader not found in current overview leaderboard",
                "leaderboardSize": len(ranks),
            }

        def _f(name: str, default: float = 0.0) -> float:
            try:
                return float(target.get(name, default) or default)
            except (TypeError, ValueError):
                return default

        def _i(name: str, default: int = 0) -> int:
            try:
                return int(target.get(name, default) or default)
            except (TypeError, ValueError):
                return default

        # OKX renamed `winRate` → `winRatio` at some point; surface both keys
        # for backward compatibility with consumers that may key off either.
        win_ratio = _f("winRatio")
        return {
            "success": True,
            "nickName": target.get("nickName") or "",
            "uniqueCode": target.get("uniqueCode") or unique_code,
            "aum": _f("aum"),
            "margin": _f("aum"),  # legacy alias
            "pnlRatio": _f("pnlRatio"),
            "profitRate": _f("pnlRatio"),  # legacy alias
            "winRatio": win_ratio,
            "winRate": win_ratio,  # legacy alias
            "copyTraderNum": _i("copyTraderNum"),
            "accCopyTraderNum": _i("accCopyTraderNum"),
            "leadDays": _i("leadDays"),
            "raw": target,
        }

    @staticmethod
    def _okx_to_binance_symbol(inst_id: str) -> str:
        """
        OKX符号转Binance符号
        BTC-USDT-SWAP -> BTCUSDT
        """
        parts = inst_id.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}{parts[1]}"
        return inst_id

    @staticmethod
    def _binance_to_okx_symbol(symbol: str) -> str:
        """
        Binance符号转OKX符号
        BTCUSDT -> BTC-USDT-SWAP
        """
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}-USDT-SWAP"
        return symbol



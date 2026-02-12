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
            sub_pos = float(item.get("subPos", 0))

            if sub_pos == 0:
                continue

            # 符号转换: BTC-USDT-SWAP -> BTCUSDT
            symbol = self._okx_to_binance_symbol(inst_id)

            positions.append({
                "symbol": symbol,
                "instId": inst_id,  # 保留原始OKX符号
                "positionSide": "LONG" if sub_pos > 0 else "SHORT",
                "positionAmt": sub_pos,
                "positionAmount": abs(sub_pos),
                "entryPrice": float(item.get("openAvgPx", 0)),
                "markPrice": float(item.get("markPx", 0)),
                "leverage": int(item.get("lever", 1)),
                "unrealizedProfit": float(item.get("upl", 0)),
                "margin": float(item.get("margin", 0)),
                "mgnMode": item.get("mgnMode", "cross"),  # cross/isolated
                "subPosId": item.get("subPosId", ""),
            })

        return positions

    async def fetch_detail(self, unique_code: str) -> Dict[str, Any]:
        """
        获取交易员详情

        API: GET /api/v5/copytrading/public-lead-traders
        """
        url = f"{self.api_base}/api/v5/copytrading/public-lead-traders"
        params = {"uniqueCode": unique_code}
        timeout = self.request_timeout_ms / 1000.0

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
                data = resp.json()

            if data.get("code") == "0":
                traders = data.get("data", [])
                if traders:
                    trader = traders[0]
                    return {
                        "success": True,
                        "nickName": trader.get("nickName", ""),
                        "uniqueCode": trader.get("uniqueCode", ""),
                        "margin": float(trader.get("margin", 0)),
                        "profitRate": float(trader.get("profitRate", 0)),
                        "winRate": float(trader.get("winRate", 0)),
                        "raw": trader,
                    }
                return {"success": False, "error": "Trader not found"}
            else:
                return {"success": False, "error": data.get("msg", "Unknown error")}
        except Exception as e:
            return {"success": False, "error": str(e)}

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



from __future__ import annotations

import re
from typing import Any, Dict, Optional


class DataUtils:
    """Utility functions for data extraction and normalization"""

    @staticmethod
    def get_str(item: Dict[str, Any], keys: tuple[str, ...]) -> str:
        """Extract string value from dict using multiple possible keys"""
        for key in keys:
            value = item.get(key)
            if value is not None:
                return str(value)
        return ""

    @staticmethod
    def get_int(item: Dict[str, Any], keys: tuple[str, ...]) -> int:
        """Extract int value from dict using multiple possible keys"""
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def normalize_ts(value: int) -> int:
        """Normalize timestamp to milliseconds"""
        if value and value < 10_000_000_000:
            return value * 1000
        return value

    @staticmethod
    def get_ts(item: Dict[str, Any], keys: tuple[str, ...]) -> int:
        """Extract and normalize timestamp from dict"""
        value = DataUtils.get_int(item, keys)
        return DataUtils.normalize_ts(value)

    @staticmethod
    def get_float(item: Dict[str, Any], keys: tuple[str, ...]) -> float:
        """Extract float value from dict using multiple possible keys"""
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    @staticmethod
    def safe_float(value: object) -> float:
        """Safely convert any value to float"""
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace(",", "").strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if match:
                try:
                    return float(match.group(0))
                except ValueError:
                    return 0.0
        return 0.0

    @staticmethod
    def safe_int(value: object, default: int = 0) -> int:
        """Safely convert any value to int"""
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        text = str(value).strip().lower().replace("x", "")
        if not text:
            return default
        try:
            return int(float(text))
        except ValueError:
            return default

    @staticmethod
    def position_signature(pos: Dict[str, Any]) -> str:
        """Generate unique signature for a position"""
        symbol = str(pos.get("symbol") or "").upper()
        side = str(pos.get("positionSide") or "BOTH").upper()
        position_amt = DataUtils.safe_float(pos.get("positionAmount"))
        entry_price = DataUtils.safe_float(pos.get("entryPrice"))
        leverage = DataUtils.safe_float(pos.get("leverage"))
        return f"{symbol}|{side}|{position_amt:.8f}|{entry_price:.6f}|{leverage:.2f}"

    @staticmethod
    def is_reduce_only(item: Dict[str, Any], position_side: str, side: str) -> bool:
        """Check if order is reduce-only"""
        flag = item.get("reduceOnly")
        if isinstance(flag, bool):
            return flag
        if isinstance(flag, str):
            return flag.lower() in {"true", "1"}
        position_side = position_side.upper()
        side = side.upper()
        if position_side == "LONG" and side == "SELL":
            return True
        if position_side == "SHORT" and side == "BUY":
            return True
        return False

    @staticmethod
    def normalize_position_side(position_side: str, position_amt: float) -> str:
        """Normalize position side based on amount"""
        side = (position_side or "").upper()
        if side in {"LONG", "SHORT"}:
            return side
        if position_amt > 0:
            return "LONG"
        if position_amt < 0:
            return "SHORT"
        return "BOTH"

    @staticmethod
    def extract_positions_data(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
        """Extract positions array from API response payload"""
        items = payload.get("positions")
        if isinstance(items, list):
            return items
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("positions") or data.get("list") or data.get("data") or []
            if isinstance(items, list):
                return items
        if isinstance(data, list):
            return data
        return []

    @staticmethod
    def position_key(symbol: str, position_side: str) -> str:
        """Generate position key from symbol and side"""
        return f"{symbol.upper()}|{position_side.upper()}"

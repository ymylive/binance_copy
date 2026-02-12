from __future__ import annotations

import math
from typing import Optional, Tuple

from .state_manager import ProjectState
from ...domain.config import ProjectConfig


class RiskCalculator:
    """Handles risk calculations including position sizing and margin ratios"""

    def __init__(self):
        pass

    def calculate_follower_qty(
        self,
        project: ProjectConfig,
        state: ProjectState,
        symbol: str,
        position_side: str,
        leader_delta: float,
        order_value: float,
        avg_price: float,
        leader_before: float,
        follower_before: float,
        leader_equity: float,
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """
        Calculate follower quantity based on scale mode.
        Returns: (follower_qty, open_pct, close_pct, follower_notional)
        """
        if order_value <= 0 or avg_price <= 0:
            return None, None, None, None

        scale_value = project.scale_value if project.scale_value > 0 else 1.0
        side = position_side.upper()
        is_reduce = False

        if leader_before and leader_delta:
            if side == "BOTH":
                is_reduce = leader_before * leader_delta < 0
            else:
                is_reduce = leader_delta < 0

        # Handle reduce-only orders
        if is_reduce:
            leader_abs = abs(leader_before)
            if leader_abs <= 0:
                return None, None, None, None
            leader_notional = leader_abs * avg_price
            if leader_notional <= 0:
                return None, None, None, None
            close_pct = min(abs(leader_delta) / leader_abs, 1.0)
            follower_qty = -abs(follower_before * close_pct)
            follower_qty = math.copysign(abs(follower_qty), -leader_before)
            follower_notional = abs(follower_before * avg_price * close_pct)
            return follower_qty, None, close_pct, follower_notional

        # Handle different scale modes
        if project.scale_mode == "fixed":
            return self._calculate_fixed_scale(
                order_value, scale_value, avg_price, leader_delta
            )
        elif project.scale_mode == "leader_margin":
            return self._calculate_leader_margin_scale(
                project, state, order_value, avg_price, leader_delta, scale_value, leader_equity
            )
        else:
            return self._calculate_ratio_scale(
                project, state, order_value, avg_price, leader_delta, scale_value, leader_equity
            )

    def _calculate_fixed_scale(
        self,
        order_value: float,
        scale_value: float,
        avg_price: float,
        leader_delta: float,
    ) -> Tuple[float, None, None, float]:
        """Calculate quantity using fixed scale mode"""
        follower_notional = order_value * scale_value
        qty = abs(follower_notional / avg_price)
        direction = 1.0 if leader_delta >= 0 else -1.0
        return direction * qty, None, None, follower_notional

    def _calculate_leader_margin_scale(
        self,
        project: ProjectConfig,
        state: ProjectState,
        order_value: float,
        avg_price: float,
        leader_delta: float,
        scale_value: float,
        leader_equity: float,
    ) -> Tuple[Optional[float], None, None, Optional[float]]:
        """Calculate quantity using leader margin scale mode"""
        if project.leader_leverage <= 0 or project.follower_leverage <= 0:
            return None, None, None, None

        follower_equity = (
            state.follower_equity
            if state.follower_equity > 0
            else project.follower_equity
        )

        if leader_equity <= 0 or follower_equity <= 0:
            return None, None, None, None

        follower_margin = (order_value / project.leader_leverage) * (
            follower_equity / leader_equity
        )
        if follower_margin <= 0:
            return None, None, None, None

        follower_notional = follower_margin * project.follower_leverage * scale_value
        if follower_notional <= 0:
            return None, None, None, None

        qty = abs(follower_notional / avg_price)
        direction = 1.0 if leader_delta >= 0 else -1.0
        return direction * qty, None, None, follower_notional

    def _calculate_ratio_scale(
        self,
        project: ProjectConfig,
        state: ProjectState,
        order_value: float,
        avg_price: float,
        leader_delta: float,
        scale_value: float,
        leader_equity: float,
    ) -> Tuple[Optional[float], Optional[float], None, Optional[float]]:
        """Calculate quantity using ratio scale mode"""
        follower_equity = (
            state.follower_equity if state.follower_equity > 0 else project.follower_equity
        )

        if (
            leader_equity <= 0
            or follower_equity <= 0
            or project.leader_leverage <= 0
            or project.follower_leverage <= 0
        ):
            return None, None, None, None

        open_pct = order_value / (leader_equity * project.leader_leverage)
        if open_pct <= 0:
            return None, None, None, None

        open_pct = min(open_pct, 1.0)
        follower_notional = (
            follower_equity * project.follower_leverage * open_pct * scale_value
        )
        if follower_notional <= 0:
            return None, None, None, None

        follower_qty = abs(follower_notional / avg_price)
        direction = 1.0 if leader_delta >= 0 else -1.0
        return direction * follower_qty, open_pct, None, follower_notional

    def apply_position_delta(
        self,
        position_side: str,
        side: str,
        qty: float,
        before: float,
    ) -> float:
        """Apply position delta and return new position"""
        delta = self.calculate_order_delta(position_side, side, qty)
        after = before + delta

        if position_side.upper() == "BOTH":
            if abs(after) < 1e-12:
                return 0.0
            return after

        return max(after, 0.0)

    def calc_margin_ratio_qty(
        self,
        position_amt: float,
        entry_price: float,
        leader_equity: float,
        follower_equity: float,
        scale_value: float,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate follower quantity based on margin ratio"""
        if position_amt <= 0 or entry_price <= 0 or leader_equity <= 0 or follower_equity <= 0:
            return None, None

        leader_notional = position_amt * entry_price
        ratio = follower_equity / leader_equity
        follower_notional = leader_notional * ratio * scale_value
        follower_qty = follower_notional / entry_price

        return follower_qty, follower_notional

    def calculate_order_delta(
        self,
        position_side: str,
        side: str,
        qty: float,
    ) -> float:
        """Calculate position delta from order"""
        side = side.upper()
        position_side = position_side.upper()

        if position_side == "BOTH":
            return qty if side == "BUY" else -qty
        elif position_side == "LONG":
            return qty if side == "BUY" else -qty
        elif position_side == "SHORT":
            return -qty if side == "SELL" else qty

        return 0.0

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

from .state_manager import ProjectState
from .position_monitor import PositionMonitor
from .order_processor import OrderProcessor
from .event_generator import EventGenerator
from .risk_calculator import RiskCalculator
from ...core.logging import get_logger
from ...domain.config import ProjectConfig
from ...domain.events import OrderEvent
from ...exchanges.binance import BinanceSession
from ...exchanges.okx import OKXSession
from ...executors.base import Executor
from ...executors.okx import OKXExecutor
from ...core.time import now_ms

logger = get_logger()


class PollerManager:
    """Orchestrates polling and copy trading operations"""

    def __init__(
        self,
        leader: BinanceSession,
        executor: Executor,
        event_sink: Callable[[OrderEvent], None],
        okx_executor: OKXExecutor | None = None,
    ) -> None:
        self._leader = leader
        self._executor = executor
        self._okx_executor = okx_executor
        self._event_sink = event_sink
        self._tasks: Dict[str, asyncio.Task] = {}
        self._states: Dict[str, ProjectState] = {}
        self._okx_sessions: Dict[str, OKXSession] = {}
        self._project_map: Dict[str, ProjectConfig] = {}

        # Initialize sub-modules
        self._position_monitor = PositionMonitor(leader, event_sink)
        self._order_processor = OrderProcessor(executor, event_sink)
        self._event_generator = EventGenerator()
        self._risk_calculator = RiskCalculator()

    def running(self) -> Dict[str, bool]:
        """Get running status of all tasks"""
        return {pid: not task.done() for pid, task in self._tasks.items()}

    def _project_key(self, project: ProjectConfig) -> str:
        base_id = project.portfolio_id
        if not base_id and project.exchange == "okx" and project.leader_id:
            base_id = project.leader_id
        if not base_id:
            return ""
        account_id = (project.trade_account_id or "").strip()
        if not account_id or account_id == "default":
            account_id = "default"
        return f"{base_id}::{account_id}"

    def _resolve_okx_session(self, project: ProjectConfig) -> OKXSession:
        key = project.leader_id or project.portfolio_id
        if key not in self._okx_sessions:
            self._okx_sessions[key] = OKXSession()
        return self._okx_sessions[key]

    def fetch_health(self) -> Dict[str, Dict[str, object]]:
        """Get health status of all portfolios"""
        return {
            pid: {
                "ok": state.last_fetch_ok,
                "ts": state.last_fetch_at,
                "error": state.last_fetch_error,
                "auth_error": state.last_fetch_auth_error,
                "backoff_ms": state.backoff_ms,
                "position_show": state.position_show,
            }
            for pid, state in self._states.items()
        }

    def poll_latency_samples(self, project_key: str) -> list[float]:
        """Return a snapshot of the rolling poll-latency window for a project.

        Returns an empty list if the project is not currently tracked. The
        caller owns the returned list (we copy out of the deque so they cannot
        mutate poller state).
        """
        state = self._states.get(project_key)
        if not state:
            return []
        return list(state.poll_latencies)

    def all_poll_latency_samples(self) -> Dict[str, list[float]]:
        """Snapshot of every tracked project's poll-latency window."""
        return {pid: list(s.poll_latencies) for pid, s in self._states.items()}

    def list_positions(self) -> list[Dict[str, object]]:
        """List all positions across portfolios"""
        results: list[Dict[str, object]] = []
        for pid, state in self._states.items():
            project = self._project_map.get(pid)
            for item in state.positions_snapshot:
                entry = dict(item)
                if project:
                    entry["portfolio_id"] = project.portfolio_id or pid
                    entry["trade_account_id"] = project.trade_account_id or "default"
                else:
                    entry["portfolio_id"] = pid
                entry["snapshot_ts"] = state.last_position_refresh
                results.append(entry)
        return results

    def list_current_positions(self) -> list[Dict[str, object]]:
        """Get current leader positions"""
        results: list[Dict[str, object]] = []
        for pid, state in self._states.items():
            project = self._project_map.get(pid)
            portfolio_id = project.portfolio_id if project else pid
            trade_account_id = project.trade_account_id if project else ""
            for key, pos in state.leader_current_positions.items():
                if not isinstance(pos, dict):
                    continue
                symbol = str(pos.get("symbol") or "")
                raw_amt = pos.get("positionAmt")
                if raw_amt is None:
                    raw_amt = pos.get("positionAmount")
                try:
                    position_amt = float(raw_amt or 0)
                except (TypeError, ValueError):
                    position_amt = 0.0
                if position_amt == 0:
                    continue
                entry_price = float(pos.get("entryPrice") or 0)
                mark_price = float(pos.get("markPrice") or 0)
                leverage = int(pos.get("leverage") or 1)
                unrealized_pnl = float(pos.get("unrealizedProfit") or 0)
                position_side = str(pos.get("positionSide") or "BOTH").upper()
                side = "LONG" if position_amt > 0 else "SHORT"
                results.append({
                    "portfolio_id": portfolio_id,
                    "trade_account_id": trade_account_id or "default",
                    "symbol": symbol,
                    "side": side,
                    "position_side": position_side,
                    "qty": abs(position_amt),
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "leverage": leverage,
                    "unrealized_pnl": unrealized_pnl,
                })
        return results

    def leader_equity(self, portfolio_id: str) -> float:
        """Get leader equity for a portfolio"""
        state = self._states.get(portfolio_id)
        if not state:
            return 0.0
        return self._calculate_leader_equity(state)

    def equity_history(self, project_id: str, limit: int = 30) -> list[float]:
        """Return the last `limit` leader-equity samples for a project.

        Used by /api/projects to populate the trader-card sparkline. Returns
        an empty list when the project has no recorded samples yet (e.g. the
        poller has not completed a detail refresh, or the project is paused).
        """
        state = self._states.get(project_id)
        if not state or not state.equity_history:
            return []
        if limit <= 0:
            return []
        samples = list(state.equity_history)
        return samples[-limit:]

    def _calculate_leader_equity(self, state: ProjectState) -> float:
        """Calculate leader equity from state"""
        if state.leader_margin > 0:
            return state.leader_margin
        if state.leader_aum > 0:
            return state.leader_aum
        return 0.0

    async def _refresh_detail(
        self,
        project: ProjectConfig,
        state: ProjectState,
        leader_session: object,
    ) -> None:
        now = now_ms()
        refresh_ms = max(project.detail_refresh_ms, 30000)
        if state.last_detail_refresh and now - state.last_detail_refresh < refresh_ms:
            return
        leader_id = project.portfolio_id
        if project.exchange == "okx" and project.leader_id:
            leader_id = project.leader_id
        try:
            detail = await leader_session.fetch_detail(leader_id)
        except Exception as exc:
            logger.warning("refresh detail failed portfolio=%s error=%s", leader_id, exc)
            return
        if not isinstance(detail, dict):
            return
        data = detail.get("data") or detail.get("raw") or detail
        if not isinstance(data, dict):
            return
        margin_raw = (
            data.get("marginBalance")
            or data.get("totalMarginBalance")
            or data.get("margin")
        )
        aum_raw = data.get("aumAmount") or data.get("aum")
        position_show = data.get("positionShow")
        if margin_raw is not None:
            try:
                state.leader_margin = float(margin_raw)
            except (TypeError, ValueError):
                pass
        if aum_raw is not None:
            try:
                state.leader_aum = float(aum_raw)
            except (TypeError, ValueError):
                pass
        if isinstance(position_show, (bool, int, float)):
            state.position_show = bool(position_show)
        state.last_detail_refresh = now
        # Record the latest leader equity sample so the trader-card sparkline
        # has real data to render. Skip zeros to avoid polluting the series
        # with empty/initial states.
        latest_equity = self._calculate_leader_equity(state)
        if latest_equity > 0:
            state.equity_history.append(float(latest_equity))

    async def _refresh_follower_equity(
        self,
        project: ProjectConfig,
        state: ProjectState,
    ) -> None:
        now = now_ms()
        refresh_ms = max(project.follower_equity_refresh_ms, 30000)
        if (
            state.last_follower_equity_refresh
            and now - state.last_follower_equity_refresh < refresh_ms
            and state.follower_equity > 0
        ):
            return
        equity: float = 0.0
        executor = self._executor
        if project.exchange == "okx" and self._okx_executor:
            executor = self._okx_executor
        try:
            balance = await executor.get_follower_balance(project.trade_account_id or None)
        except Exception as exc:
            logger.warning(
                "refresh follower balance failed account=%s error=%s",
                project.trade_account_id or "default",
                exc,
            )
            balance = None
        if balance:
            equity = (
                balance.get("margin_balance")
                or balance.get("available_balance")
                or balance.get("wallet_balance")
                or 0.0
            )
        if equity <= 0:
            try:
                equity = await executor.get_follower_equity(project.trade_account_id or None) or 0.0
            except Exception as exc:
                logger.warning(
                    "refresh follower equity failed account=%s error=%s",
                    project.trade_account_id or "default",
                    exc,
                )
        if equity > 0:
            allocated_pct = project.allocated_equity_pct or 0.0
            state.follower_equity = equity * (allocated_pct / 100.0)
            state.last_follower_equity_refresh = now
            return
        state.follower_equity = project.follower_equity

    async def start_project(self, project: ProjectConfig) -> None:
        """Start polling for a project"""
        project_id = self._project_key(project)
        if not project_id:
            logger.warning("Project has no valid ID, skipping")
            return
        if project_id in self._tasks:
            logger.warning("Already polling portfolio=%s", project_id)
            return

        bootstrap = now_ms() - max(project.order_window_ms, 120000)
        state = ProjectState(last_order_time=bootstrap)
        self._states[project_id] = state
        self._project_map[project_id] = project

        task = asyncio.create_task(self._run_polling_loop(project, state))
        self._tasks[project_id] = task

        logger.info("Started polling portfolio=%s", project_id)

    async def stop_project(self, portfolio_id: str) -> None:
        """Stop polling for a portfolio"""
        task = self._tasks.pop(portfolio_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._states.pop(portfolio_id, None)
        self._project_map.pop(portfolio_id, None)
        logger.info("Stopped polling portfolio=%s", portfolio_id)

    async def _run_polling_loop(self, project: ProjectConfig, state: ProjectState) -> None:
        """Main polling loop for a project"""
        while True:
            try:
                leader_session = self._leader
                if project.exchange == "okx":
                    leader_session = self._resolve_okx_session(project)
                leader_now = self._get_leader_time_ms(leader_session)

                await self._refresh_detail(project, state, leader_session)
                await self._refresh_follower_equity(project, state)
                leader_equity = self._calculate_leader_equity(state)

                # Run position monitoring
                await self._position_monitor.run_position_monitor(
                    project,
                    state,
                    leader_now,
                    leader_session=leader_session,
                    leader_equity=leader_equity,
                )

                # Wait before next poll
                await asyncio.sleep(3)  # 3 second polling interval

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Polling error portfolio=%s error=%s",
                    project.portfolio_id,
                    exc,
                    exc_info=True,
                )
                await asyncio.sleep(5)  # Back off on error

    def _get_leader_time_ms(self, session: object = None) -> int:
        """Get current time with leader's time offset"""
        from ...core.time import now_ms
        target = session or self._leader
        offset = getattr(target, "time_offset_ms", 0)
        return now_ms() + offset

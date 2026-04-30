from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from ..core.logging import get_logger
from ..core.time import now_ms
from ..domain.config import (
    ConfigPatch,
    LeaderConfig,
    LeaderSubscription,
    ProjectConfig,
    SignalConfig,
    OnchainConfig,
)
from ..domain.events import OrderEvent
from ..domain.trade import TradingAccount
from ..executors.binance import ApiExecutor
from ..executors.okx import OKXExecutor
from ..executors.router import RoutedExecutor
from ..exchanges.binance import BinanceSession
from ..exchanges.leader_proxy import LeaderProxyClient
from ..services.config_store import ConfigStore
from ..services.project_store import ProjectStore
from ..services.migration import migrate_app_config, migrate_trade_config, needs_migration
from ..services.poller import PollerManager
from ..services.onchain import OnchainManager
from ..services.signal_manager import SignalManager
from ..domain.onchain import OnchainEvent

logger = get_logger()


class AppState:
    def __init__(self, config_store: ConfigStore | None = None) -> None:
        self._config_store = config_store or ConfigStore()
        self.config = self._config_store.load()
        self._project_store = ProjectStore()

        # Auto-migrate if needed
        self._auto_migrate()
        self._load_projects_from_store()

        self.okx_executor = OKXExecutor()
        self.executor = RoutedExecutor(ApiExecutor(), self.okx_executor)
        self.events = deque(maxlen=1000)
        self.onchain_events = deque(maxlen=1000)
        self.leader = self._build_leader()
        self.poller = PollerManager(
            self.leader,
            self.executor,
            self._add_event,
            okx_executor=self.okx_executor,
        )
        self.signal_manager = SignalManager(
            self.config.signal,
            self.executor,
            self._add_event,
        )
        self.onchain = OnchainManager(self.config.onchain, self._add_onchain_event)
        self._log_task: asyncio.Task | None = None

    def _auto_migrate(self) -> None:
        """Auto-migrate old config format to new account-centric format."""
        config_dict = self.config.model_dump()
        if not needs_migration(config_dict):
            return

        logger.info("Detected old config format, starting auto-migration...")

        # Migrate app config
        config_path = Path(self._config_store.config_path)
        self.config = migrate_app_config(self.config, config_path)
        self._config_store.save(self.config)

        # Migrate trade config if exists
        trade_config_path = Path(self._config_store.trade_config_path)
        if trade_config_path.exists():
            trade_config = self._config_store.load_trade_config()
            migrated_trade = migrate_trade_config(trade_config, self.config, trade_config_path)
            self._config_store.save_trade_config(migrated_trade)

        logger.info("Migration completed successfully")

    def _load_projects_from_store(self) -> None:
        stored = self._project_store.list_projects()
        if stored:
            normalized = False
            for project in stored:
                if self._normalize_project_ids(project):
                    normalized = True
            self.config.projects = stored
            self._config_store.save(self.config)
            if normalized:
                for project in stored:
                    self._project_store.upsert_project(project)
            return
        if self.config.projects:
            normalized = False
            for project in self.config.projects:
                if self._normalize_project_ids(project):
                    normalized = True
            if normalized:
                self._config_store.save(self.config)
            self._project_store.seed_if_empty(self.config.projects)

    def _normalize_project_ids(self, project: ProjectConfig) -> bool:
        updated = False
        if project.portfolio_id:
            cleaned = project.portfolio_id.strip()
            if cleaned != project.portfolio_id:
                project.portfolio_id = cleaned
                updated = True
        if project.leader_id:
            cleaned = project.leader_id.strip()
            if cleaned != project.leader_id:
                project.leader_id = cleaned
                updated = True
        if project.trade_account_id is not None:
            cleaned = project.trade_account_id.strip()
            if cleaned == "default":
                cleaned = ""
            if cleaned != project.trade_account_id:
                project.trade_account_id = cleaned
                updated = True
        if project.leader_id and not project.portfolio_id:
            project.portfolio_id = project.leader_id
            updated = True
        if project.exchange == "okx" and project.portfolio_id and not project.leader_id:
            project.leader_id = project.portfolio_id
            updated = True
        return updated
    def _build_leader(self) -> BinanceSession | LeaderProxyClient:
        if self.config.leader_source == "proxy":
            return LeaderProxyClient(
                self.config.leader_proxy_base,
                timeout_ms=self.config.leader_proxy_timeout_ms,
            )
        return BinanceSession(
            self.config.cdp_url,
            self.config.api_base,
            auth_mode=self.config.auth_mode,
            cookie_path=self.config.cookie_path,
            user_agent=self.config.user_agent,
            extra_headers=self.config.leader_headers,
            request_timeout_ms=self.config.request_timeout_ms,
        )

    def _add_event(self, event: OrderEvent) -> None:
        if event.status != "queued":
            return
        if event.action not in {"open", "add", "reduce", "close"}:
            return
        self.events.appendleft(event)
        logger.info(
            "order action=%s symbol=%s side=%s position=%s qty=%.6f price=%.6f value=%.4f status=%s portfolio=%s",
            event.action,
            event.symbol,
            event.side,
            event.position_side or "-",
            event.follower_qty,
            event.avg_price,
            event.order_value,
            event.status,
            event.portfolio_id,
        )

    def _add_onchain_event(self, event: OnchainEvent) -> None:
        self.onchain_events.appendleft(event)
        logger.info(
            "onchain event chain=%s wallet=%s mint=%s direction=%s amount=%.6f sig=%s",
            event.chain,
            event.wallet,
            event.mint,
            event.direction,
            event.token_change,
            event.signature,
        )

    def _format_ts(self, ms: int) -> str:
        if not ms:
            return "-"
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def _collect_recent_actions(self, limit: int = 50) -> Dict[str, int]:
        counts = {"open": 0, "add": 0, "reduce": 0, "close": 0}
        for event in list(self.events)[:limit]:
            if event.action in counts:
                counts[event.action] += 1
        return counts

    def _summarize_fetch_health(self, now: int) -> Dict[str, object]:
        health = self.poller.fetch_health()
        summary = {
            "status": "idle",
            "ok": 0,
            "fail": 0,
            "stale": 0,
            "auth_error": False,
            "position_hidden": False,
            "last_error": "",
            "max_backoff_ms": 0,
        }
        if not health:
            return summary

        stale_threshold_ms = 15000
        ok_count = 0
        fail_count = 0
        stale_count = 0
        auth_error = False
        position_hidden = False
        last_error = ""
        max_backoff = 0
        for project_id, info in health.items():
            ts = int(info.get("ts") or 0)
            ok = bool(info.get("ok"))
            err = str(info.get("error") or "").strip()
            backoff = int(info.get("backoff_ms") or 0)
            max_backoff = max(max_backoff, backoff)
            if info.get("auth_error"):
                auth_error = True
            if err == "position_hidden":
                try:
                    project = self.resolve_project(project_id) if project_id else None
                    if project and project.monitor_mode == "position":
                        position_hidden = True
                except KeyError:
                    pass
            if not ts or now - ts > stale_threshold_ms:
                stale_count += 1
                if err and not last_error:
                    last_error = f"{project_id}:{err}"
                continue
            if ok:
                ok_count += 1
                continue
            fail_count += 1
            if err and not last_error:
                last_error = f"{project_id}:{err}"

        status = "ok" if ok_count > 0 and fail_count == 0 and stale_count == 0 else "degraded"
        summary.update(
            {
                "status": status,
                "ok": ok_count,
                "fail": fail_count,
                "stale": stale_count,
                "auth_error": auth_error,
                "position_hidden": position_hidden,
                "last_error": last_error,
                "max_backoff_ms": max_backoff,
            }
        )
        return summary

    def summarize_fetch_health(self, now: int | None = None) -> Dict[str, object]:
        if now is None:
            now = now_ms()
        return self._summarize_fetch_health(now)

    def record_event(self, event: OrderEvent) -> None:
        self._add_event(event)

    def update_signal(self, event_id: str, **fields) -> None:
        """Patch a recorded signal with mirror execution outcome.

        Surface for upstream callers (poller / API / SSE) to attach mirror lifecycle
        updates after the executor has returned. The executor itself mutates the
        OrderEvent in place during execute(), so this is for out-of-band patches
        (e.g. delayed exchange ack, manual reclassification).

        Silently ignores unknown event_ids and unknown field names — callers
        should not need defensive try/except, and we never raise on a stale id
        because events.deque has maxlen and old events get evicted naturally.
        """
        if not event_id:
            return
        for evt in self.events:
            if evt.event_id == event_id:
                for key, value in fields.items():
                    if hasattr(evt, key):
                        setattr(evt, key, value)
                return

    def _cookie_status(self, fetch_summary: Dict[str, object]) -> str:
        if not self._config_store.cookie_exists(self.config):
            return "missing"
        if fetch_summary.get("status") == "idle":
            return "unknown"
        if fetch_summary.get("auth_error"):
            return "invalid"
        return "ok"

    def _log_tracking_status(self) -> None:
        try:
            running = self.poller.running()
            running_count = sum(1 for active in running.values() if active)
            counts = self._collect_recent_actions()
            now = now_ms()
            fetch_summary = self._summarize_fetch_health(now)
            cookie_status = self._cookie_status(fetch_summary)
            header_status = None
            if hasattr(self.leader, "header_status"):
                try:
                    header_status = self.leader.header_status()
                except Exception:
                    header_status = None
            last_action = "-"
            last_symbol = "-"
            last_time = "-"
            if self.events:
                last_event = self.events[0]
                last_action = last_event.action or "-"
                last_symbol = last_event.symbol or "-"
                last_time = self._format_ts(last_event.created_at)
            last_error = self.leader.last_error or "-"
            hdr_token = "-" if not header_status else header_status.get("has_fvideo_token")
            hdr_device = "-" if not header_status else header_status.get("has_device_info")
            hdr_csrf = "-" if not header_status else header_status.get("has_csrftoken")
            hdr_waf = "-" if not header_status else header_status.get("has_waf_cookie")
            logger.info(
                "tracking connected=%s auth=%s cookie=%s fetch=%s ok=%d fail=%d stale=%d backoff=%dms running=%d events=%d recent(open=%d add=%d reduce=%d close=%d) last=%s %s %s error=%s fetch_error=%s hdr(token=%s device=%s csrf=%s waf=%s)",
                self.leader.connected,
                self.config.auth_mode,
                cookie_status,
                fetch_summary.get("status"),
                fetch_summary.get("ok") or 0,
                fetch_summary.get("fail") or 0,
                fetch_summary.get("stale") or 0,
                fetch_summary.get("max_backoff_ms") or 0,
                running_count,
                len(self.events),
                counts["open"],
                counts["add"],
                counts["reduce"],
                counts["close"],
                last_action,
                last_symbol,
                last_time,
                last_error,
                fetch_summary.get("last_error") or "-",
                hdr_token,
                hdr_device,
                hdr_csrf,
                hdr_waf,
            )
        except Exception:
            logger.exception("tracking log failed")

    async def _log_tracking_loop(self) -> None:
        while True:
            self._log_tracking_status()
            await asyncio.sleep(10)

    def _ensure_log_task(self) -> None:
        if self._log_task and not self._log_task.done():
            return
        self._log_task = asyncio.create_task(self._log_tracking_loop())

    async def _stop_log_task(self) -> None:
        if not self._log_task:
            return
        self._log_task.cancel()
        try:
            await self._log_task
        except asyncio.CancelledError:
            pass
        self._log_task = None

    async def start(self) -> None:
        await self.leader.connect()
        for project in self.config.projects:
            if project.enabled:
                await self.poller.start_project(project)
        self._ensure_log_task()
        await self.signal_manager.start()
        await self.onchain.start()

    async def stop(self) -> None:
        await self._stop_log_task()
        for portfolio_id in list(self.poller.running().keys()):
            await self.poller.stop_project(portfolio_id)
        await self.signal_manager.stop()
        await self.onchain.stop()
        await self.leader.close()

    def list_projects(self) -> List[ProjectConfig]:
        return list(self.config.projects)

    def get_project(self, portfolio_id: str) -> ProjectConfig:
        return self.resolve_project(portfolio_id)

    def resolve_project(self, identifier: str) -> ProjectConfig:
        key = (identifier or "").strip()
        if not key:
            raise KeyError(identifier)
        if "::" in key:
            base_id, account_id = key.split("::", 1)
            account_key = self._account_key(account_id)
            for project in self.config.projects:
                if (
                    (project.portfolio_id == base_id or project.leader_id == base_id)
                    and self._account_key(project.trade_account_id) == account_key
                ):
                    return project
            raise KeyError(identifier)
        matches = [
            project
            for project in self.config.projects
            if project.portfolio_id == key or project.leader_id == key
        ]
        if len(matches) == 1:
            return matches[0]
        for project in matches:
            if self._account_key(project.trade_account_id) == "default":
                return project
        raise KeyError(identifier)

    def project_key(self, project: ProjectConfig) -> str:
        base_id = project.portfolio_id or project.leader_id or ""
        if not base_id:
            return ""
        account_key = self._account_key(project.trade_account_id)
        return f"{base_id}::{account_key}"

    def _account_key(self, value: str | None) -> str:
        cleaned = (value or "").strip()
        if not cleaned or cleaned == "default":
            return "default"
        return cleaned

    def upsert_project(self, project: ProjectConfig) -> None:
        self._normalize_project_ids(project)
        target_key = self.project_key(project)
        for idx, existing in enumerate(self.config.projects):
            if self.project_key(existing) == target_key:
                self.config.projects[idx] = project
                self._config_store.save(self.config)
                self._project_store.upsert_project(project)
                return
        self.config.projects.append(project)
        self._config_store.save(self.config)
        self._project_store.upsert_project(project)

    async def update_config(self, patch: ConfigPatch) -> None:
        updates = patch.model_dump(exclude_none=True)
        if not updates:
            return
        new_config = self.config.model_copy(update=updates)
        self._config_store.save(new_config)
        await self.stop()
        self.config = new_config
        self._load_projects_from_store()
        self.leader = self._build_leader()
        self.poller = PollerManager(
            self.leader,
            self.executor,
            self._add_event,
            okx_executor=self.okx_executor,
        )
        self.signal_manager = SignalManager(
            self.config.signal,
            self.executor,
            self._add_event,
        )
        self.onchain = OnchainManager(self.config.onchain, self._add_onchain_event)
        await self.start()

    async def update_signal_config(self, config: SignalConfig) -> None:
        new_config = self.config.model_copy(update={"signal": config})
        self._config_store.save(new_config)
        await self.signal_manager.stop()
        self.config = new_config
        self.signal_manager = SignalManager(
            self.config.signal,
            self.executor,
            self._add_event,
        )
        await self.signal_manager.start()

    async def update_onchain_config(self, config: OnchainConfig) -> None:
        new_config = self.config.model_copy(update={"onchain": config})
        self._config_store.save(new_config)
        await self.onchain.update_config(config)
        self.config = new_config

    def remove_project(self, identifier: str) -> None:
        project = self.resolve_project(identifier)
        target_key = self.project_key(project)
        self.config.projects = [
            project
            for project in self.config.projects
            if self.project_key(project) != target_key
        ]
        self._config_store.save(self.config)
        self._project_store.delete_project(project.portfolio_id, project.trade_account_id)

    # Leader management methods
    def list_leaders(self) -> List[LeaderConfig]:
        return list(self.config.leaders)

    def get_leader(self, leader_id: str) -> LeaderConfig:
        for leader in self.config.leaders:
            if leader.leader_id == leader_id:
                return leader
        raise KeyError(leader_id)

    def upsert_leader(self, leader: LeaderConfig) -> None:
        for idx, existing in enumerate(self.config.leaders):
            if existing.leader_id == leader.leader_id:
                self.config.leaders[idx] = leader
                self._config_store.save(self.config)
                return
        self.config.leaders.append(leader)
        self._config_store.save(self.config)

    def remove_leader(self, leader_id: str) -> None:
        self.config.leaders = [
            leader for leader in self.config.leaders if leader.leader_id != leader_id
        ]
        self._config_store.save(self.config)

    # Account management methods
    def list_accounts(self) -> List[TradingAccount]:
        trade_config = self._config_store.load_trade_config()
        accounts = list(trade_config.accounts)
        default_id = trade_config.default_account_id
        if default_id:
            accounts.sort(key=lambda account: 0 if account.account_id == default_id else 1)
        return accounts

    def get_account(self, account_id: str) -> TradingAccount:
        trade_config = self._config_store.load_trade_config()
        for account in trade_config.accounts:
            if account.account_id == account_id:
                return account
        raise KeyError(account_id)

    def upsert_account(self, account: TradingAccount) -> None:
        trade_config = self._config_store.load_trade_config()
        if account.enabled and not trade_config.enabled:
            trade_config.enabled = True
        if not trade_config.default_account_id or trade_config.default_account_id == "default":
            trade_config.default_account_id = account.account_id
        for idx, existing in enumerate(trade_config.accounts):
            if existing.account_id == account.account_id:
                trade_config.accounts[idx] = account
                self._config_store.save_trade_config(trade_config)
                return
        trade_config.accounts.append(account)
        self._config_store.save_trade_config(trade_config)

    def remove_account(self, account_id: str) -> None:
        trade_config = self._config_store.load_trade_config()
        trade_config.accounts = [
            account for account in trade_config.accounts if account.account_id != account_id
        ]
        self._config_store.save_trade_config(trade_config)

    # Subscription management methods
    def add_leader_subscription(self, account_id: str, subscription: LeaderSubscription) -> None:
        account = self.get_account(account_id)
        # Remove existing subscription if present
        account.leader_subscriptions = [
            sub for sub in account.leader_subscriptions if sub.leader_id != subscription.leader_id
        ]
        account.leader_subscriptions.append(subscription)
        self.upsert_account(account)

    def remove_leader_subscription(self, account_id: str, leader_id: str) -> None:
        account = self.get_account(account_id)
        account.leader_subscriptions = [
            sub for sub in account.leader_subscriptions if sub.leader_id != leader_id
        ]
        self.upsert_account(account)

"""Migration utilities for converting old config format to new account-centric format."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.domain.config import AppConfig, LeaderConfig, LeaderSubscription
from app.domain.trade import TradingAccount, TradeConfig


def needs_migration(config_data: Dict[str, Any]) -> bool:
    """Check if config needs migration from project-based to account-centric."""
    projects = config_data.get("projects") or []
    leaders = config_data.get("leaders") or []
    return bool(projects) and not leaders


def migrate_app_config(old_config: AppConfig, config_path: Path) -> AppConfig:
    """Migrate AppConfig from project-based to account-centric format."""
    if not old_config.projects:
        return old_config

    # Backup old config
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.with_suffix(f".backup_{timestamp}.json")
    shutil.copy2(config_path, backup_path)

    # Create leader registry from projects
    leaders = []
    for project in old_config.projects:
        if not project.leader_id:
            project.leader_id = f"leader_{project.portfolio_id}"

        leader = LeaderConfig(
            leader_id=project.leader_id,
            exchange=project.exchange,
            portfolio_id=project.portfolio_id,
            name=f"Leader {project.portfolio_id}",
            enabled=project.enabled
        )
        leaders.append(leader)

    # Create new config with leaders but keep projects intact.
    new_config = old_config.model_copy()
    new_config.leaders = leaders

    return new_config


def migrate_trade_config(old_trade_config: TradeConfig, old_app_config: AppConfig, config_path: Path) -> TradeConfig:
    """Migrate TradeConfig to add leader subscriptions to accounts."""
    if not old_app_config.projects:
        return old_trade_config

    # Backup old config
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.with_suffix(f".backup_{timestamp}.json")
    shutil.copy2(config_path, backup_path)

    # Map project settings to account subscriptions
    new_accounts = []
    for account in old_trade_config.accounts:
        # Find projects that use this account
        subscriptions = []
        for project in old_app_config.projects:
            if project.trade_account_id == account.account_id or (not project.trade_account_id and account.account_id == "default"):
                if not project.leader_id:
                    project.leader_id = f"leader_{project.portfolio_id}"

                subscription = LeaderSubscription(
                    leader_id=project.leader_id,
                    enabled=project.enabled,
                    allocated_equity_pct=project.allocated_equity_pct,
                    follower_leverage=project.follower_leverage,
                    scale_mode=project.scale_mode,
                    scale_value=project.scale_value,
                    monitor_mode=project.monitor_mode,
                    poll_interval_ms=project.poll_interval_ms
                )
                subscriptions.append(subscription)

        # Create new account with subscriptions
        new_account = TradingAccount(
            account_id=account.account_id,
            name=account.name,
            exchange=getattr(account, "exchange", "binance"),
            enabled=account.enabled,
            base_url=account.base_url,
            api_key=account.api_key,
            api_secret=account.api_secret,
            recv_window=account.recv_window,
            timeout_ms=account.timeout_ms,
            min_qty=account.min_qty,
            max_qty=account.max_qty,
            send_position_side=account.send_position_side,
            order_type=account.order_type,
            time_sync=account.time_sync,
            time_sync_interval_ms=account.time_sync_interval_ms,
            auto_adjust_qty=account.auto_adjust_qty,
            min_notional_mode=account.min_notional_mode,
            exchange_info_ttl_ms=account.exchange_info_ttl_ms,
            price_ttl_ms=account.price_ttl_ms,
            auto_position_mode=account.auto_position_mode,
            position_mode_ttl_ms=account.position_mode_ttl_ms,
            auto_set_leverage=account.auto_set_leverage,
            leverage_ttl_ms=account.leverage_ttl_ms,
            usdt_order_mode=account.usdt_order_mode,
            price_source=account.price_source,
            leader_subscriptions=subscriptions
        )
        new_accounts.append(new_account)

    # Create new trade config
    new_trade_config = TradeConfig(
        enabled=old_trade_config.enabled,
        default_account_id=old_trade_config.default_account_id,
        accounts=new_accounts
    )

    return new_trade_config

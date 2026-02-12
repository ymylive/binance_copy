from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

from ..core.paths import PROJECT_DB_PATH
from ..domain.config import ProjectConfig


class ProjectStore:
    def __init__(self, path: Path = PROJECT_DB_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            columns = conn.execute("PRAGMA table_info(projects)").fetchall()
            if not columns:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS projects (
                        portfolio_id TEXT,
                        trade_account_id TEXT DEFAULT '',
                        exchange TEXT,
                        leader_id TEXT,
                        enabled INTEGER,
                        monitor_mode TEXT,
                        poll_interval_ms INTEGER,
                        order_window_ms INTEGER,
                        page_size INTEGER,
                        scale_mode TEXT,
                        scale_value REAL,
                        leader_leverage REAL,
                        follower_leverage REAL,
                        follower_equity REAL,
                        follower_equity_refresh_ms INTEGER,
                        min_qty REAL,
                        max_qty REAL,
                        detail_refresh_ms INTEGER,
                        allocated_equity_pct REAL,
                        PRIMARY KEY (portfolio_id, trade_account_id)
                    )
                    """
                )
                return

            pk_columns = [row["name"] for row in columns if row["pk"]]
            if pk_columns == ["portfolio_id"]:
                conn.execute("ALTER TABLE projects RENAME TO projects_legacy")
                conn.execute(
                    """
                    CREATE TABLE projects (
                        portfolio_id TEXT,
                        trade_account_id TEXT DEFAULT '',
                        exchange TEXT,
                        leader_id TEXT,
                        enabled INTEGER,
                        monitor_mode TEXT,
                        poll_interval_ms INTEGER,
                        order_window_ms INTEGER,
                        page_size INTEGER,
                        scale_mode TEXT,
                        scale_value REAL,
                        leader_leverage REAL,
                        follower_leverage REAL,
                        follower_equity REAL,
                        follower_equity_refresh_ms INTEGER,
                        min_qty REAL,
                        max_qty REAL,
                        detail_refresh_ms INTEGER,
                        allocated_equity_pct REAL,
                        PRIMARY KEY (portfolio_id, trade_account_id)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO projects (
                        portfolio_id,
                        trade_account_id,
                        exchange,
                        leader_id,
                        enabled,
                        monitor_mode,
                        poll_interval_ms,
                        order_window_ms,
                        page_size,
                        scale_mode,
                        scale_value,
                        leader_leverage,
                        follower_leverage,
                        follower_equity,
                        follower_equity_refresh_ms,
                        min_qty,
                        max_qty,
                        detail_refresh_ms,
                        allocated_equity_pct
                    )
                    SELECT
                        portfolio_id,
                        COALESCE(trade_account_id, ''),
                        exchange,
                        leader_id,
                        enabled,
                        monitor_mode,
                        poll_interval_ms,
                        order_window_ms,
                        page_size,
                        scale_mode,
                        scale_value,
                        leader_leverage,
                        follower_leverage,
                        follower_equity,
                        follower_equity_refresh_ms,
                        min_qty,
                        max_qty,
                        detail_refresh_ms,
                        allocated_equity_pct
                    FROM projects_legacy
                    """
                )
                conn.execute("DROP TABLE projects_legacy")

    def _project_to_row(self, project: ProjectConfig) -> Dict[str, object]:
        return {
            "portfolio_id": project.portfolio_id,
            "exchange": project.exchange,
            "leader_id": project.leader_id,
            "enabled": 1 if project.enabled else 0,
            "monitor_mode": project.monitor_mode,
            "poll_interval_ms": int(project.poll_interval_ms),
            "order_window_ms": int(project.order_window_ms),
            "page_size": int(project.page_size),
            "scale_mode": project.scale_mode,
            "scale_value": float(project.scale_value),
            "leader_leverage": float(project.leader_leverage),
            "follower_leverage": float(project.follower_leverage),
            "trade_account_id": project.trade_account_id,
            "follower_equity": float(project.follower_equity),
            "follower_equity_refresh_ms": int(project.follower_equity_refresh_ms),
            "min_qty": float(project.min_qty),
            "max_qty": float(project.max_qty),
            "detail_refresh_ms": int(project.detail_refresh_ms),
            "allocated_equity_pct": float(project.allocated_equity_pct),
        }

    def _row_to_project(self, row: sqlite3.Row) -> ProjectConfig:
        payload = dict(row)
        payload["enabled"] = bool(payload.get("enabled"))
        return ProjectConfig(**payload)

    def list_projects(self) -> List[ProjectConfig]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects").fetchall()
        return [self._row_to_project(row) for row in rows]

    def upsert_project(self, project: ProjectConfig) -> None:
        data = self._project_to_row(project)
        columns = list(data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        updates = ", ".join(
            f"{column}=excluded.{column}"
            for column in columns
            if column not in {"portfolio_id", "trade_account_id"}
        )
        values = [data[column] for column in columns]
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO projects ({", ".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(portfolio_id, trade_account_id) DO UPDATE SET {updates}
                """,
                values,
            )

    def delete_project(self, portfolio_id: str, trade_account_id: str | None = None) -> None:
        account_id = (trade_account_id or "").strip()
        if account_id == "default":
            account_id = ""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM projects WHERE portfolio_id = ? AND trade_account_id = ?",
                (portfolio_id, account_id),
            )

    def seed_if_empty(self, projects: List[ProjectConfig]) -> None:
        if not projects:
            return
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS count FROM projects").fetchone()
            if row and int(row["count"]) > 0:
                return
        for project in projects:
            self.upsert_project(project)

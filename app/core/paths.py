from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
CONFIG_PATH = ROOT_DIR / "config.json"
TRADE_CONFIG_PATH = ROOT_DIR / "trade_config.json"
OKX_TRADE_CONFIG_PATH = ROOT_DIR / "okx_trade_config.json"
DATA_DIR = ROOT_DIR / "data"
PROJECT_DB_PATH = DATA_DIR / "projects.db"

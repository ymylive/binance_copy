from __future__ import annotations

from pathlib import Path

from ..core.paths import CONFIG_PATH, ROOT_DIR, TRADE_CONFIG_PATH
from ..core.storage import load_json, save_json
from ..domain.config import AppConfig
from ..domain.trade import TradeConfig


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH, trade_path: Path = TRADE_CONFIG_PATH) -> None:
        self._path = path
        self._trade_path = trade_path

    @property
    def config_path(self) -> Path:
        return self._path

    @property
    def trade_config_path(self) -> Path:
        return self._trade_path

    def load(self) -> AppConfig:
        return load_json(self._path, AppConfig, AppConfig())

    def save(self, config: AppConfig) -> None:
        save_json(self._path, config)

    def load_trade_config(self) -> TradeConfig:
        return load_json(self._trade_path, TradeConfig, TradeConfig())

    def save_trade_config(self, config: TradeConfig) -> None:
        save_json(self._trade_path, config)

    def resolve_cookie_path(self, value: str) -> Path:
        candidate = (ROOT_DIR / value).resolve()
        if ROOT_DIR not in candidate.parents and candidate != ROOT_DIR:
            raise ValueError("cookie_path is outside project root")
        return candidate

    def cookie_exists(self, config: AppConfig) -> bool:
        try:
            path = self.resolve_cookie_path(config.cookie_path or "cookies.json")
        except ValueError:
            return False
        return path.exists()

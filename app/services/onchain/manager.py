from __future__ import annotations

import asyncio
from typing import Callable, Dict

from ...core.logging import get_logger
from ...domain.config import OnchainConfig, OnchainWalletConfig
from ...domain.onchain import OnchainEvent
from .solana import SolanaWatcher, DEFAULT_IGNORE_MINTS

logger = get_logger()


class OnchainManager:
    def __init__(
        self,
        config: OnchainConfig,
        event_sink: Callable[[OnchainEvent], None],
    ) -> None:
        self._config = config
        self._event_sink = event_sink
        self._tasks: Dict[str, asyncio.Task] = {}
        self._watchers: Dict[str, SolanaWatcher] = {}

    async def start(self) -> None:
        if not self._config.enabled:
            return
        if self._config.chain != "solana":
            logger.warning("unsupported onchain chain=%s", self._config.chain)
            return
        for wallet in self._config.wallets:
            if not wallet.enabled or not wallet.address:
                continue
            await self._start_wallet(wallet)

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self._watchers.clear()

    async def update_config(self, config: OnchainConfig) -> None:
        await self.stop()
        self._config = config
        await self.start()

    async def _start_wallet(self, wallet: OnchainWalletConfig) -> None:
        if wallet.address in self._tasks:
            return
        ignore_mints = self._config.ignore_mints or list(DEFAULT_IGNORE_MINTS)
        watcher = SolanaWatcher(
            rpc_url=self._config.rpc_url,
            wallet=wallet.address,
            poll_interval_ms=self._config.poll_interval_ms,
            ignore_mints=ignore_mints,
            event_sink=self._event_sink,
        )
        self._watchers[wallet.address] = watcher
        self._tasks[wallet.address] = asyncio.create_task(watcher.start())
        logger.info("onchain watcher started wallet=%s", wallet.address)

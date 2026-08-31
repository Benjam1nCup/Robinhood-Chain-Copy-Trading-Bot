"""Unified wallet transaction monitor."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from bot.chain import Chain
from bot.config import AppConfig
from bot.models import RawTransaction
from bot.monitor.blocks import BlockMonitor

log = logging.getLogger("rh_copy")


class WalletMonitor:
    def __init__(self, chain: Chain, cfg: AppConfig) -> None:
        self.chain = chain
        self.cfg = cfg
        wallets = cfg.enabled_wallets()
        self.targets = {w.address.lower() for w in wallets}
        self._block = BlockMonitor(chain, cfg, self.targets)

    async def listen(self) -> AsyncIterator[RawTransaction]:
        if not self.targets:
            log.warning("[MONITOR] no enabled target wallets — add addresses to config/wallets.json")
        log.info("[MONITOR] tracking %s wallet(s)", len(self.targets))
        async for tx in self._block.listen():
            if tx.tx_hash:
                yield tx

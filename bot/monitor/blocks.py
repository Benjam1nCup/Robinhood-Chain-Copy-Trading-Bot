"""Poll new blocks for transactions from target wallets."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

from bot.chain import Chain
from bot.config import AppConfig
from bot.models import RawTransaction

log = logging.getLogger("rh_copy")


class BlockMonitor:
    def __init__(self, chain: Chain, cfg: AppConfig, targets: set[str]) -> None:
        self.chain = chain
        self.cfg = cfg
        self.targets = {a.lower() for a in targets}
        self._last_block: int | None = None

    def _resolve_start(self) -> int:
        assert self.chain.w3 is not None
        latest = int(self.chain.w3.eth.block_number)
        start = self.cfg.monitor.start_block
        if start == "latest":
            return latest
        try:
            return int(start)
        except ValueError:
            return latest

    async def listen(self) -> AsyncIterator[RawTransaction]:
        assert self.chain.w3 is not None
        if self._last_block is None:
            self._last_block = self._resolve_start()
            log.info("[MONITOR] starting at block %s", self._last_block)

        while True:
            latest = int(self.chain.w3.eth.block_number)
            while self._last_block <= latest:
                block_num = self._last_block
                try:
                    block = self.chain.get_block(block_num)
                    ts = float(block.get("timestamp") or time.time())
                    for tx in block.get("transactions") or []:
                        frm = (tx.get("from") or "").lower()
                        if frm not in self.targets:
                            continue
                        tx_hash = tx.get("hash")
                        hx = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
                        inp = tx.get("input") or b""
                        data = inp.hex() if isinstance(inp, bytes) else str(inp)
                        if data.startswith("0x"):
                            data = data[2:]
                        yield RawTransaction(
                            tx_hash=hx if hx.startswith("0x") else f"0x{hx}",
                            from_address=frm,
                            to_address=(tx.get("to") or "").lower(),
                            value=int(tx.get("value") or 0),
                            input_data=data,
                            block_number=block_num,
                            timestamp=ts,
                            gas_price=int(tx.get("gasPrice") or tx.get("maxFeePerGas") or 0),
                        )
                except Exception as exc:
                    log.warning("[MONITOR] block %s error: %s", block_num, exc)
                self._last_block += 1
            await asyncio.sleep(self.cfg.chain.poll_blocks_s)

"""WebSocket block subscription when WS URL is configured."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

import websockets

from bot.config import AppConfig
from bot.models import RawTransaction

log = logging.getLogger("rh_copy")


class WebSocketMonitor:
    def __init__(self, cfg: AppConfig, targets: set[str]) -> None:
        self.cfg = cfg
        self.targets = {a.lower() for a in targets}
        self.ws_url = cfg.chain.ws_url or cfg.chain.sequencer_feed

    async def listen(self) -> AsyncIterator[RawTransaction]:
        if not self.ws_url:
            raise RuntimeError("no websocket URL configured")
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                    sub = {"jsonrpc": "2.0", "id": 1, "method": "eth_subscribe", "params": ["newHeads"]}
                    await ws.send(json.dumps(sub))
                    log.info("[WS] subscribed %s", self.ws_url)
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("method") != "eth_subscription":
                            continue
                        # WS monitor only signals new heads; block polling handles tx decode
                        yield RawTransaction(
                            tx_hash="",
                            from_address="",
                            to_address="",
                            value=0,
                            input_data="",
                            block_number=int(msg.get("params", {}).get("result", {}).get("number", "0x0"), 16),
                            timestamp=time.time(),
                        )
            except Exception as exc:
                log.warning("[WS] disconnected: %s — retry in 5s", exc)
                await asyncio.sleep(5)

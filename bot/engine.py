"""Main copy-trading engine."""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

from bot.chain import Chain
from bot.config import AppConfig
from bot.data.prices import PriceService
from bot.data.tokens import TokenRegistry
from bot.decoder.swaps import SwapDecoder
from bot.execution.executor import TradeExecutor
from bot.logging_setup import setup_logging
from bot.models import TxStatus
from bot.monitor.wallet_monitor import WalletMonitor
from bot.portfolio.positions import PortfolioManager
from bot.store import Store
from bot.strategy.risk import RiskEngine
from bot.strategy_engine import CopyStrategy
from bot.zerox import ZeroXClient

log = logging.getLogger("rh_copy")


class CopyTradingEngine:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.chain = Chain(cfg)
        self.store = Store()
        self.session: aiohttp.ClientSession | None = None
        self.registry: TokenRegistry | None = None
        self.prices: PriceService | None = None
        self.portfolio = PortfolioManager(self.store, cfg.bot.paper_starting_usdg)
        self.monitor: WalletMonitor | None = None
        self.decoder: SwapDecoder | None = None
        self.strategy: CopyStrategy | None = None
        self.risk: RiskEngine | None = None
        self.executor: TradeExecutor | None = None
        self.zerox: ZeroXClient | None = None
        self._seen: set[str] = set()
        self._running = False

    async def start(self) -> None:
        setup_logging(self.cfg.bot.log_level, self.cfg.bot.log_file, self.cfg.bot.log_timestamp_name)
        log.info("[ENGINE] Robinhood Chain Copy Trading Bot starting")
        log.info("[ENGINE] mode=%s dry_run=%s live=%s", "paper" if self.cfg.bot.paper_trading else "live", self.cfg.bot.dry_run, self.cfg.live_enabled)

        if not self.chain.connect():
            raise RuntimeError("failed to connect to Robinhood Chain RPC")

        self._seen = self.store.load_seen_tx()
        self.session = aiohttp.ClientSession()
        self.registry = TokenRegistry(self.cfg, self.session)
        await self.registry.refresh(force=True)
        self.prices = PriceService(self.cfg, self.session, self.chain)
        self.zerox = ZeroXClient(self.cfg, self.session)
        self.monitor = WalletMonitor(self.chain, self.cfg)
        self.decoder = SwapDecoder(self.chain, self.cfg, self.registry)
        self.strategy = CopyStrategy(self.cfg, self.registry, self.prices, self.portfolio)
        self.risk = RiskEngine(self.cfg, self.chain, self.portfolio)
        self.executor = TradeExecutor(self.chain, self.cfg, self.zerox)

        self._running = True
        refresh_task = asyncio.create_task(self._refresh_tokens())
        heartbeat_task = asyncio.create_task(self._heartbeat())
        try:
            await self._run_loop()
        finally:
            self._running = False
            refresh_task.cancel()
            heartbeat_task.cancel()
            self.store.save_seen_tx(self._seen)

    async def close(self) -> None:
        if self.session:
            await self.session.close()

    async def _refresh_tokens(self) -> None:
        assert self.registry is not None
        while self._running:
            try:
                await self.registry.refresh()
            except Exception as exc:
                log.warning("[TOKENS] refresh failed: %s", exc)
            await asyncio.sleep(self.cfg.stock_tokens.refresh_interval_s)

    async def _heartbeat(self) -> None:
        while self._running:
            wallets = len(self.cfg.enabled_wallets())
            positions = len(self.portfolio.open_positions())
            block = self.chain.w3.eth.block_number if self.chain.w3 else 0
            log.info("[HEARTBEAT] block=%s wallets=%s positions=%s seen_tx=%s", block, wallets, positions, len(self._seen))
            await asyncio.sleep(self.cfg.bot.heartbeat_s)

    async def _run_loop(self) -> None:
        assert self.monitor and self.decoder and self.strategy and self.risk and self.executor
        async for raw in self.monitor.listen():
            hx = raw.tx_hash.lower()
            if hx in self._seen:
                continue
            self.store.mark_seen(hx, self._seen)

            trade = self.decoder.decode(raw)
            if not trade:
                continue

            log.info(
                "[DETECT] wallet=%s tx=%s %s %s→%s",
                trade.wallet[:10],
                trade.tx_hash[:14],
                trade.side.value,
                trade.symbol_in or trade.token_in[:8],
                trade.symbol_out or trade.token_out[:8],
            )

            decision = await self.strategy.decide(trade)
            self.store.append_trade(
                {
                    "ts": time.time(),
                    "wallet": trade.wallet,
                    "tx_hash": trade.tx_hash,
                    "side": trade.side.value,
                    "token_in": trade.token_in,
                    "token_out": trade.token_out,
                    "approved": decision.approved,
                    "reasons": decision.reasons,
                }
            )
            if not decision.approved:
                continue

            ok, risk_reasons = self.risk.validate(decision)
            if not ok:
                log.info("[RISK] reject %s: %s", trade.tx_hash[:14], "; ".join(risk_reasons))
                continue

            fill = await self.executor.execute_copy(trade, decision.copy_size_usd)
            if fill.ok:
                self.portfolio.record_fill(fill, trade, paper=self.cfg.bot.paper_trading)
                log.info("[COPY] done %s venue=%s status=%s", trade.tx_hash[:14], fill.venue, fill.status.value)
            else:
                log.error("[COPY] failed %s: %s", trade.tx_hash[:14], fill.error)

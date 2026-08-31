"""Copy strategy orchestration — analyze, filter, size."""

from __future__ import annotations

import logging
from decimal import Decimal

from bot.config import AppConfig
from bot.data.prices import PriceService
from bot.data.tokens import TokenRegistry
from bot.models import CopyAnalysis, CopyDecision, SwapTrade, TradeSide, TxStatus
from bot.portfolio.positions import PortfolioManager
from bot.strategy.filters import apply_filters
from bot.strategy.sizing import calculate_copy_size_usd
from bot.strategy.wallet_score import wallet_score

log = logging.getLogger("rh_copy")


class CopyStrategy:
    def __init__(
        self,
        cfg: AppConfig,
        registry: TokenRegistry,
        prices: PriceService,
        portfolio: PortfolioManager,
    ) -> None:
        self.cfg = cfg
        self.registry = registry
        self.prices = prices
        self.portfolio = portfolio

    async def analyze(self, trade: SwapTrade) -> CopyAnalysis:
        wallet_cfg = self.cfg.wallet_map().get(trade.wallet)
        score = wallet_score(wallet_cfg, self.portfolio.store) if wallet_cfg else 0.0

        sym = trade.symbol_out if trade.side != TradeSide.SELL else trade.symbol_in
        token = trade.token_out if trade.side != TradeSide.SELL else trade.token_in
        official = trade.official_out if trade.side != TradeSide.SELL else trade.official_in
        mult = self.registry.multiplier(token)
        amt_ui = trade.amount_out_ui if trade.side != TradeSide.SELL else trade.amount_in_ui

        est_usd = await self.prices.usd_value(token, sym, amt_ui, official, mult)
        if self.prices.stable_token(trade.token_in):
            est_usd = trade.amount_in_ui if trade.side != TradeSide.SELL else est_usd

        liquidity = Decimal(str(self.cfg.copy_settings.min_liquidity_usd)) * Decimal("2")

        return CopyAnalysis(
            should_copy=False,
            wallet_score=score,
            liquidity_usd=liquidity,
            estimated_value_usd=est_usd,
        )

    async def decide(self, trade: SwapTrade) -> CopyDecision:
        wallet_cfg = self.cfg.wallet_map().get(trade.wallet)
        if not wallet_cfg or not wallet_cfg.enabled:
            return CopyDecision(False, trade, reasons=["wallet not enabled"], status=TxStatus.REJECTED)

        analysis = await self.analyze(trade)
        ok, reasons = apply_filters(trade, self.cfg, wallet_cfg, analysis)
        if not ok:
            log.info("[STRATEGY] skip %s: %s", trade.tx_hash[:14], "; ".join(reasons))
            return CopyDecision(False, trade, reasons=reasons, status=TxStatus.REJECTED)

        portfolio_usd = self.portfolio.portfolio_usd(paper=self.cfg.bot.paper_trading)
        size_usd = calculate_copy_size_usd(trade, analysis.estimated_value_usd, self.cfg, wallet_cfg, portfolio_usd)
        if size_usd <= 0:
            return CopyDecision(False, trade, reasons=["copy size below minimum"], status=TxStatus.REJECTED)

        log.info(
            "[STRATEGY] APPROVE %s %s %s→%s size=$%s score=%.0f",
            trade.side.value,
            trade.tx_hash[:14],
            trade.symbol_in or trade.token_in[:8],
            trade.symbol_out or trade.token_out[:8],
            size_usd,
            analysis.wallet_score,
        )
        return CopyDecision(True, trade, copy_size_usd=size_usd, status=TxStatus.APPROVED)

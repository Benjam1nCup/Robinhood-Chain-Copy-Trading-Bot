"""Trade filtering rules."""

from __future__ import annotations

import time

from bot.config import AppConfig, TargetWallet
from bot.models import CopyAnalysis, SwapTrade


def apply_filters(
    trade: SwapTrade,
    cfg: AppConfig,
    wallet: TargetWallet,
    analysis: CopyAnalysis,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    age = time.time() - trade.timestamp
    analysis.trade_age_s = age

    if age > cfg.copy_settings.max_trade_age_s:
        reasons.append(f"trade too old ({age:.1f}s > {cfg.copy_settings.max_trade_age_s}s)")

    bl = {t.lower() for t in cfg.copy_settings.token_blacklist}
    if trade.token_in.lower() in bl or trade.token_out.lower() in bl:
        reasons.append("token blacklisted")

    if cfg.copy_settings.require_official_token and not (trade.official_in or trade.official_out):
        reasons.append("not an official Robinhood Stock Token")

    if analysis.wallet_score < cfg.risk.min_wallet_score:
        reasons.append(f"wallet score {analysis.wallet_score:.0f} < {cfg.risk.min_wallet_score}")

    if analysis.liquidity_usd > 0 and analysis.estimated_value_usd > 0:
        ratio = float(analysis.estimated_value_usd / analysis.liquidity_usd)
        if ratio > cfg.copy_settings.max_liquidity_ratio:
            reasons.append(f"liquidity ratio {ratio:.2%} > {cfg.copy_settings.max_liquidity_ratio:.2%}")

    if analysis.estimated_value_usd <= 0:
        reasons.append("zero trade value")

    if trade.side.value == "SELL" and not cfg.copy_settings.copy_exits:
        reasons.append("exit copying disabled")

    return len(reasons) == 0, reasons

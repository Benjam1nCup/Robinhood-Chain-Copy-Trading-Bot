"""Position sizing — proportional, fixed, and hybrid."""

from __future__ import annotations

from decimal import Decimal

from bot.config import AppConfig, TargetWallet
from bot.models import SwapTrade


def calculate_copy_size_usd(
    trade: SwapTrade,
    estimated_trade_usd: Decimal,
    cfg: AppConfig,
    wallet: TargetWallet,
    portfolio_usd: Decimal,
) -> Decimal:
    ratio = wallet.copy_ratio if wallet.copy_ratio is not None else cfg.copy_settings.copy_ratio
    max_pos = wallet.max_position_usd if wallet.max_position_usd is not None else cfg.copy_settings.max_position_usd

    mode = cfg.copy_settings.sizing_mode.lower()
    if mode == "fixed":
        size = Decimal(str(cfg.copy_settings.fixed_size_usd))
    elif mode in {"proportional", "hybrid"}:
        size = estimated_trade_usd * Decimal(str(ratio))
    else:
        prop = estimated_trade_usd * Decimal(str(ratio))
        fixed = Decimal(str(cfg.copy_settings.fixed_size_usd))
        size = min(prop, fixed) if prop > 0 else fixed

    size = min(size, Decimal(str(max_pos)))
    if size < Decimal(str(cfg.copy_settings.min_position_usd)):
        return Decimal("0")
    return size.quantize(Decimal("0.01"))

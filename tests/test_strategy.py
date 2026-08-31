"""Tests for copy trading bot core logic."""

from decimal import Decimal

from bot.config import AppConfig, TargetWallet
from bot.models import CopyAnalysis, SwapTrade, TradeSide
from bot.strategy.filters import apply_filters
from bot.strategy.sizing import calculate_copy_size_usd


def _trade(**kwargs) -> SwapTrade:
    defaults = dict(
        wallet="0xabc",
        tx_hash="0x123",
        block_number=1,
        timestamp=1_700_000_000,
        router="0xrouter",
        token_in="0xusdg",
        token_out="0xaapl",
        amount_in=1_000_000,
        amount_out=10**18,
        decimals_in=6,
        decimals_out=18,
        symbol_in="USDG",
        symbol_out="AAPL",
        side=TradeSide.BUY,
        official_out=True,
    )
    defaults.update(kwargs)
    return SwapTrade(**defaults)


def test_hybrid_sizing_caps_at_max():
    cfg = AppConfig()
    wallet = TargetWallet(address="0xabc", max_position_usd=200, copy_ratio=0.5)
    size = calculate_copy_size_usd(_trade(), Decimal("5000"), cfg, wallet, Decimal("10000"))
    assert size == Decimal("200.00")


def test_filter_rejects_old_trade():
    cfg = AppConfig()
    cfg.copy_settings.max_trade_age_s = 10
    wallet = TargetWallet(address="0xabc", score=80)
    trade = _trade(timestamp=1)
    analysis = CopyAnalysis(should_copy=False, wallet_score=80, estimated_value_usd=Decimal("100"), liquidity_usd=Decimal("100000"))
    ok, reasons = apply_filters(trade, cfg, wallet, analysis)
    assert not ok
    assert any("old" in r for r in reasons)


def test_filter_approves_fresh_trade():
    import time

    cfg = AppConfig()
    wallet = TargetWallet(address="0xabc", score=80)
    trade = _trade(timestamp=time.time())
    analysis = CopyAnalysis(should_copy=False, wallet_score=80, estimated_value_usd=Decimal("100"), liquidity_usd=Decimal("100000"))
    ok, reasons = apply_filters(trade, cfg, wallet, analysis)
    assert ok
    assert reasons == []

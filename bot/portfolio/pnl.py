"""Unrealized PnL helpers."""

from __future__ import annotations

from decimal import Decimal

from bot.models import Position


def unrealized_pnl(pos: Position, mark_price: Decimal) -> Decimal:
    if mark_price <= 0:
        return Decimal("0")
    return pos.amount_token * mark_price - pos.cost_usd


def unrealized_pct(pos: Position, mark_price: Decimal) -> Decimal:
    if pos.cost_usd <= 0:
        return Decimal("0")
    return unrealized_pnl(pos, mark_price) / pos.cost_usd * Decimal("100")

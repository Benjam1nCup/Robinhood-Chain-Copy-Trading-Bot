"""Gas balance checks."""

from __future__ import annotations

from decimal import Decimal

from bot.chain import Chain
from bot.config import AppConfig


def native_balance_eth(chain: Chain) -> Decimal:
    if not chain.connected:
        return Decimal("0")
    return Decimal(chain.native_balance()) / Decimal(10**18)


def has_min_gas(chain: Chain, cfg: AppConfig) -> bool:
    return native_balance_eth(chain) >= Decimal(str(cfg.copy_settings.min_gas_balance_eth))

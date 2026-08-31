"""Risk engine — gas, exposure, daily loss, emergency stop."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from bot.chain import Chain
from bot.config import AppConfig
from bot.models import CopyDecision, SwapTrade
from bot.portfolio.positions import PortfolioManager

log = logging.getLogger("rh_copy")


class RiskEngine:
    def __init__(self, cfg: AppConfig, chain: Chain, portfolio: PortfolioManager) -> None:
        self.cfg = cfg
        self.chain = chain
        self.portfolio = portfolio

    def emergency_stop(self) -> bool:
        if self.cfg.bot.stop_trading:
            return True
        stop_file = Path(self.cfg.risk.emergency_stop_file)
        return stop_file.exists()

    def gas_ok(self) -> tuple[bool, str]:
        if not self.chain.connected:
            return True, ""
        bal_wei = self.chain.native_balance()
        bal_eth = Decimal(bal_wei) / Decimal(10**18)
        min_eth = Decimal(str(self.cfg.copy_settings.min_gas_balance_eth))
        if bal_eth < min_eth:
            return False, f"gas balance {bal_eth:.6f} ETH < {min_eth} ETH"
        return True, ""

    def daily_loss_ok(self) -> tuple[bool, str]:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        row = self.portfolio.store.load_daily_pnl()
        if row.get("date") != today:
            return True, ""
        loss = Decimal(str(row.get("realized_loss_usd") or 0))
        max_loss = Decimal(str(self.cfg.copy_settings.max_daily_loss_usd))
        if loss >= max_loss:
            return False, f"daily loss ${loss} >= ${max_loss}"
        return True, ""

    def token_exposure_ok(self, token: str, add_usd: Decimal) -> tuple[bool, str]:
        exposure = self.portfolio.token_exposure_usd(token)
        max_exp = Decimal(str(self.cfg.copy_settings.max_token_exposure_usd))
        if exposure + add_usd > max_exp:
            return False, f"token exposure ${exposure + add_usd} > ${max_exp}"
        return True, ""

    def validate(self, decision: CopyDecision) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if self.emergency_stop():
            reasons.append("emergency stop active")
        ok, msg = self.gas_ok()
        if not ok:
            reasons.append(msg)
        ok, msg = self.daily_loss_ok()
        if not ok:
            reasons.append(msg)
        token = decision.trade.token_out if decision.trade.side.value == "BUY" else decision.trade.token_in
        ok, msg = self.token_exposure_ok(token, decision.copy_size_usd)
        if not ok:
            reasons.append(msg)
        if decision.copy_size_usd <= 0:
            reasons.append("copy size zero")
        return len(reasons) == 0, reasons

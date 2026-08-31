"""Shared dataclasses for the copy-trading pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SWAP = "SWAP"


class TxStatus(str, Enum):
    DETECTED = "DETECTED"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUBMITTING = "SUBMITTING"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    PAPER = "PAPER"


@dataclass
class RawTransaction:
    tx_hash: str
    from_address: str
    to_address: str
    value: int
    input_data: str
    block_number: int
    timestamp: float
    gas_price: int = 0


@dataclass
class SwapTrade:
    wallet: str
    tx_hash: str
    block_number: int
    timestamp: float
    router: str
    token_in: str
    token_out: str
    amount_in: int
    amount_out: int
    decimals_in: int = 18
    decimals_out: int = 18
    symbol_in: str = ""
    symbol_out: str = ""
    side: TradeSide = TradeSide.SWAP
    official_in: bool = False
    official_out: bool = False
    fee_tier: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def amount_in_ui(self) -> Decimal:
        return Decimal(self.amount_in) / (Decimal(10) ** self.decimals_in)

    @property
    def amount_out_ui(self) -> Decimal:
        return Decimal(self.amount_out) / (Decimal(10) ** self.decimals_out)


@dataclass
class CopyAnalysis:
    should_copy: bool
    reasons: list[str] = field(default_factory=list)
    wallet_score: float = 0.0
    trade_age_s: float = 0.0
    liquidity_usd: Decimal = Decimal("0")
    estimated_value_usd: Decimal = Decimal("0")
    slippage_bps: int = 0


@dataclass
class CopyDecision:
    approved: bool
    trade: SwapTrade
    copy_size_usd: Decimal = Decimal("0")
    copy_amount_in: int = 0
    reasons: list[str] = field(default_factory=list)
    status: TxStatus = TxStatus.VALIDATING


@dataclass
class Position:
    position_id: str
    token: str
    symbol: str
    amount_token: Decimal
    cost_usd: Decimal
    entry_price: Decimal
    opened_at: float
    source_wallet: str
    source_tx: str
    tx_hash: str | None = None
    status: str = "open"
    decimals: int = 18
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fill:
    ok: bool
    venue: str
    tx_hash: str | None
    amount_in: Decimal
    amount_out: Decimal
    price: Decimal
    status: TxStatus
    error: str = ""
    trade: SwapTrade | None = None

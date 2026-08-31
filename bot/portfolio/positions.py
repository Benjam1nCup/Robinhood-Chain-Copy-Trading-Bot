"""Position tracking and exit-ratio logic."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from bot.models import Fill, Position, SwapTrade, TradeSide
from bot.store import Store

log = logging.getLogger("rh_copy")


class PortfolioManager:
    def __init__(self, store: Store, paper_start_usdg: float = 5000.0) -> None:
        self.store = store
        self.paper_start = Decimal(str(paper_start_usdg))
        self._positions: dict[str, Position] = {}
        self._load()

    def _load(self) -> None:
        for row in self.store.load_positions():
            if row.get("status") != "open":
                continue
            pos = Position(
                position_id=row["position_id"],
                token=row["token"],
                symbol=row.get("symbol", ""),
                amount_token=Decimal(str(row["amount_token"])),
                cost_usd=Decimal(str(row["cost_usd"])),
                entry_price=Decimal(str(row["entry_price"])),
                opened_at=float(row["opened_at"]),
                source_wallet=row.get("source_wallet", ""),
                source_tx=row.get("source_tx", ""),
                tx_hash=row.get("tx_hash"),
                status=row.get("status", "open"),
                decimals=int(row.get("decimals", 18)),
            )
            self._positions[pos.token.lower()] = pos

    def _persist(self) -> None:
        rows = []
        for p in self._positions.values():
            rows.append(
                {
                    "position_id": p.position_id,
                    "token": p.token,
                    "symbol": p.symbol,
                    "amount_token": str(p.amount_token),
                    "cost_usd": str(p.cost_usd),
                    "entry_price": str(p.entry_price),
                    "opened_at": p.opened_at,
                    "source_wallet": p.source_wallet,
                    "source_tx": p.source_tx,
                    "tx_hash": p.tx_hash,
                    "status": p.status,
                    "decimals": p.decimals,
                }
            )
        self.store.save_positions(rows)

    def portfolio_usd(self, paper: bool = True) -> Decimal:
        if paper:
            pw = self.store.load_paper_wallet()
            return Decimal(str(pw.get("usdg", self.paper_start)))
        return self.paper_start

    def token_exposure_usd(self, token: str) -> Decimal:
        pos = self._positions.get(token.lower())
        return pos.cost_usd if pos else Decimal("0")

    def record_fill(self, fill: Fill, trade: SwapTrade, paper: bool = True) -> None:
        if not fill.ok:
            return
        token_key = trade.token_out.lower() if trade.side != TradeSide.SELL else trade.token_in.lower()
        symbol = trade.symbol_out if trade.side != TradeSide.SELL else trade.symbol_in

        if trade.side == TradeSide.SELL:
            pos = self._positions.get(trade.token_in.lower())
            if not pos:
                return
            sell_ratio = trade.amount_in_ui / pos.amount_token if pos.amount_token else Decimal("1")
            sell_ratio = min(sell_ratio, Decimal("1"))
            sold_qty = pos.amount_token * sell_ratio
            proceeds = fill.amount_out
            pos.amount_token -= sold_qty
            pos.cost_usd -= pos.cost_usd * sell_ratio
            if pos.amount_token <= Decimal("0.0000001"):
                pos.status = "closed"
                del self._positions[trade.token_in.lower()]
            log.info("[PORTFOLIO] SELL %s ratio=%.2f%% proceeds=$%s", symbol, float(sell_ratio * 100), proceeds)
        else:
            existing = self._positions.get(token_key)
            if existing:
                total_qty = existing.amount_token + fill.amount_out
                total_cost = existing.cost_usd + fill.amount_in
                existing.amount_token = total_qty
                existing.cost_usd = total_cost
                existing.entry_price = total_cost / total_qty if total_qty else Decimal("0")
            else:
                self._positions[token_key] = Position(
                    position_id=str(uuid.uuid4()),
                    token=trade.token_out,
                    symbol=symbol,
                    amount_token=fill.amount_out,
                    cost_usd=fill.amount_in,
                    entry_price=fill.price,
                    opened_at=trade.timestamp,
                    source_wallet=trade.wallet,
                    source_tx=trade.tx_hash,
                    tx_hash=fill.tx_hash,
                    decimals=trade.decimals_out,
                )
            log.info("[PORTFOLIO] BUY %s qty=%s cost=$%s", symbol, fill.amount_out, fill.amount_in)

        if paper:
            pw = self.store.load_paper_wallet()
            usdg = Decimal(str(pw.get("usdg", self.paper_start)))
            tokens = pw.get("tokens") or {}
            if trade.side == TradeSide.SELL:
                usdg += fill.amount_out
            else:
                usdg -= fill.amount_in
            tok = tokens.get(token_key, "0")
            tok_amt = Decimal(str(tok))
            if trade.side == TradeSide.SELL:
                tok_amt -= fill.amount_in
            else:
                tok_amt += fill.amount_out
            tokens[token_key] = str(tok_amt)
            self.store.save_paper_wallet({"usdg": str(usdg), "tokens": tokens})

        self._persist()

    def open_positions(self) -> list[Position]:
        return list(self._positions.values())

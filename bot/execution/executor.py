"""Build, sign, and broadcast copy trades."""

from __future__ import annotations

import logging
from decimal import Decimal

from web3 import Web3

from bot.abis import QUOTER_V2_ABI, SWAP_ROUTER_02_ABI
from bot.chain import Chain
from bot.config import AppConfig
from bot.constants import USDG_DECIMALS
from bot.execution.approvals import ApprovalManager
from bot.execution.nonce import NonceManager
from bot.models import Fill, SwapTrade, TradeSide, TxStatus
from bot.zerox import ZeroXClient, implied_price

log = logging.getLogger("rh_copy")


def _to_wei(ui: Decimal, decimals: int) -> int:
    return int(ui * (Decimal(10) ** decimals))


def _from_wei(raw: int, decimals: int) -> Decimal:
    return Decimal(raw) / (Decimal(10) ** decimals)


class TradeExecutor:
    def __init__(self, chain: Chain, cfg: AppConfig, zerox: ZeroXClient | None) -> None:
        self.chain = chain
        self.cfg = cfg
        self.zerox = zerox
        self.nonce_mgr = NonceManager()
        self.approvals = ApprovalManager(chain, cfg, self.nonce_mgr)

    def _mode(self) -> str:
        if self.cfg.bot.paper_trading:
            return "paper"
        if self.cfg.bot.dry_run or not self.cfg.live_enabled:
            return "dry_run"
        return "live"

    async def execute_copy(self, trade: SwapTrade, size_usd: Decimal) -> Fill:
        if trade.side == TradeSide.SELL:
            return await self._execute_sell(trade, size_usd)
        return await self._execute_buy(trade, size_usd)

    async def _execute_buy(self, trade: SwapTrade, size_usd: Decimal) -> Fill:
        mode = self._mode()
        sell_token = self.cfg.uniswap.usdg
        buy_token = trade.token_out
        sell_dec = USDG_DECIMALS
        buy_dec = trade.decimals_out

        if mode == "paper":
            px = size_usd / trade.amount_out_ui if trade.amount_out_ui else Decimal("1")
            tokens = size_usd / px if px else Decimal("0")
            log.info("[EXEC] PAPER BUY %s $%s", trade.symbol_out or buy_token[:10], size_usd)
            return Fill(True, "paper", None, size_usd, tokens, px, TxStatus.PAPER, trade=trade)

        if mode == "dry_run":
            log.info("[EXEC] DRY-RUN BUY %s $%s", trade.symbol_out or buy_token[:10], size_usd)
            return Fill(True, "dry_run", None, size_usd, Decimal("0"), Decimal("0"), TxStatus.APPROVED, trade=trade)

        sell_amount = _to_wei(size_usd, sell_dec)
        if trade.official_out and self.cfg.execution.prefer_zerox_for_official and self.zerox and self.zerox.enabled:
            fill = await self._zerox_swap(sell_token, buy_token, sell_amount, sell_dec, buy_dec, size_usd, trade)
            if fill.ok:
                return fill

        return await self._uniswap_buy(trade, size_usd, sell_amount, buy_dec)

    async def _execute_sell(self, trade: SwapTrade, size_usd: Decimal) -> Fill:
        mode = self._mode()
        sell_token = trade.token_in
        buy_token = self.cfg.uniswap.usdg
        sell_dec = trade.decimals_in
        buy_dec = USDG_DECIMALS

        if mode == "paper":
            log.info("[EXEC] PAPER SELL %s ~$%s", trade.symbol_in or sell_token[:10], size_usd)
            return Fill(True, "paper", None, trade.amount_in_ui, size_usd, Decimal("0"), TxStatus.PAPER, trade=trade)

        if mode == "dry_run":
            log.info("[EXEC] DRY-RUN SELL %s", trade.symbol_in or sell_token[:10])
            return Fill(True, "dry_run", None, trade.amount_in_ui, Decimal("0"), Decimal("0"), TxStatus.APPROVED, trade=trade)

        sell_amount = _to_wei(trade.amount_in_ui, sell_dec)
        if trade.official_in and self.zerox and self.zerox.enabled:
            fill = await self._zerox_swap(sell_token, buy_token, sell_amount, sell_dec, buy_dec, size_usd, trade)
            if fill.ok:
                return fill
        return await self._uniswap_sell(trade, sell_amount, buy_dec)

    async def _zerox_swap(
        self, sell_token: str, buy_token: str, sell_amount: int, sell_dec: int, buy_dec: int, size_usd: Decimal, trade: SwapTrade
    ) -> Fill:
        assert self.zerox is not None
        q = await self.zerox.quote(
            sell_token=sell_token,
            buy_token=buy_token,
            sell_amount=sell_amount,
            taker=self.chain.address,
            slippage_bps=self.cfg.copy_settings.max_slippage_bps,
        )
        if not q:
            return Fill(False, "zerox", None, size_usd, Decimal("0"), Decimal("0"), TxStatus.FAILED, "no quote", trade)
        tx = q.get("transaction") or {}
        px = implied_price(q, sell_dec, buy_dec)
        out = _from_wei(int(q.get("buyAmount") or 0), buy_dec)
        spender = (q.get("issues") or {}).get("allowance", {}).get("spender") or tx.get("to")
        return self._broadcast_raw(
            to=tx.get("to"),
            data=tx.get("data"),
            value=int(tx.get("value") or 0),
            gas=int(tx.get("gas") or self.cfg.execution.gas_limit),
            venue="zerox",
            amount_in=size_usd,
            amount_out=out,
            price=px,
            sell_token=sell_token,
            spender=spender or "",
            sell_amount=sell_amount,
            trade=trade,
        )

    async def _uniswap_buy(self, trade: SwapTrade, size_usd: Decimal, sell_amount: int, buy_dec: int) -> Fill:
        fee = trade.fee_tier or 3000
        quoted = self._quote_v3(self.cfg.uniswap.usdg, trade.token_out, sell_amount, fee)
        min_out = quoted * (10_000 - self.cfg.copy_settings.max_slippage_bps) // 10_000 if quoted else 0
        router = self.chain.contract(self.cfg.uniswap.swap_router_02, SWAP_ROUTER_02_ABI)
        params = (
            self.chain.checksum(self.cfg.uniswap.usdg),
            self.chain.checksum(trade.token_out),
            int(fee),
            self.chain.checksum(self.chain.address),
            sell_amount,
            min_out,
            0,
        )
        fn = router.functions.exactInputSingle(params)
        out = _from_wei(quoted or 0, buy_dec)
        px = size_usd / out if out else Decimal("0")
        return self._broadcast_fn(
            fn,
            venue="uniswap_v3",
            amount_in=size_usd,
            amount_out=out,
            price=px,
            sell_token=self.cfg.uniswap.usdg,
            spender=self.cfg.uniswap.swap_router_02,
            sell_amount=sell_amount,
            trade=trade,
        )

    async def _uniswap_sell(self, trade: SwapTrade, sell_amount: int, buy_dec: int) -> Fill:
        fee = trade.fee_tier or 3000
        quoted = self._quote_v3(trade.token_in, self.cfg.uniswap.usdg, sell_amount, fee)
        min_out = quoted * (10_000 - self.cfg.copy_settings.max_slippage_bps) // 10_000 if quoted else 0
        router = self.chain.contract(self.cfg.uniswap.swap_router_02, SWAP_ROUTER_02_ABI)
        params = (
            self.chain.checksum(trade.token_in),
            self.chain.checksum(self.cfg.uniswap.usdg),
            int(fee),
            self.chain.checksum(self.chain.address),
            sell_amount,
            min_out,
            0,
        )
        fn = router.functions.exactInputSingle(params)
        proceeds = _from_wei(quoted or 0, buy_dec)
        px = proceeds / trade.amount_in_ui if trade.amount_in_ui else Decimal("0")
        return self._broadcast_fn(
            fn,
            venue="uniswap_v3",
            amount_in=trade.amount_in_ui,
            amount_out=proceeds,
            price=px,
            sell_token=trade.token_in,
            spender=self.cfg.uniswap.swap_router_02,
            sell_amount=sell_amount,
            trade=trade,
        )

    def _quote_v3(self, token_in: str, token_out: str, amount_in: int, fee: int) -> int:
        try:
            quoter = self.chain.contract(self.cfg.uniswap.quoter_v2, QUOTER_V2_ABI)
            params = (
                self.chain.checksum(token_in),
                self.chain.checksum(token_out),
                amount_in,
                int(fee),
                0,
            )
            result = quoter.functions.quoteExactInputSingle(params).call()
            return int(result[0] if isinstance(result, (list, tuple)) else result)
        except Exception as exc:
            log.debug("[EXEC] quoter: %s", exc)
            return 0

    def _broadcast_fn(self, fn, *, venue: str, amount_in: Decimal, amount_out: Decimal, price: Decimal, sell_token: str, spender: str, sell_amount: int, trade: SwapTrade) -> Fill:
        if sell_token and spender and sell_amount:
            if not self.approvals.ensure(sell_token, spender, sell_amount):
                return Fill(False, venue, None, amount_in, Decimal("0"), price, TxStatus.FAILED, "approve failed", trade)
        tx = fn.build_transaction(
            {
                "from": self.chain.address,
                "nonce": self.nonce_mgr.next(self.chain.w3, self.chain.address),
                "gas": self.cfg.execution.gas_limit,
                "chainId": self.cfg.chain.chain_id,
            }
        )
        return self._sign_send(tx, venue, amount_in, amount_out, price, trade)

    def _broadcast_raw(self, *, to: str, data: str, value: int, gas: int, venue: str, amount_in: Decimal, amount_out: Decimal, price: Decimal, sell_token: str, spender: str, sell_amount: int, trade: SwapTrade) -> Fill:
        if not to or not data:
            return Fill(False, venue, None, amount_in, Decimal("0"), price, TxStatus.FAILED, "empty tx", trade)
        if sell_token and spender and sell_amount:
            if not self.approvals.ensure(sell_token, spender, sell_amount):
                return Fill(False, venue, None, amount_in, Decimal("0"), price, TxStatus.FAILED, "approve failed", trade)
        tx = {
            "from": self.chain.address,
            "to": Web3.to_checksum_address(to),
            "data": data,
            "value": value,
            "nonce": self.nonce_mgr.next(self.chain.w3, self.chain.address),
            "gas": gas or self.cfg.execution.gas_limit,
            "chainId": self.cfg.chain.chain_id,
        }
        return self._sign_send(tx, venue, amount_in, amount_out, price, trade)

    def _sign_send(self, tx: dict, venue: str, amount_in: Decimal, amount_out: Decimal, price: Decimal, trade: SwapTrade) -> Fill:
        w3 = self.chain.w3
        assert w3 is not None and self.chain.account is not None
        try:
            signed = self.chain.account.sign_transaction(tx)
            raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
            txh = w3.eth.send_raw_transaction(raw)
            hx = txh.hex() if hasattr(txh, "hex") else str(txh)
            log.info("[TX] BROADCAST %s %s %s", venue, hx, self.chain.explorer_tx(hx))
            rcpt = w3.eth.wait_for_transaction_receipt(txh, timeout=self.cfg.execution.tx_confirm_timeout_s)
            status = int(rcpt.get("status") if isinstance(rcpt, dict) else rcpt.status)
            if status != 1:
                return Fill(False, venue, hx, amount_in, Decimal("0"), price, TxStatus.FAILED, "reverted", trade)
            log.info("[TX] CONFIRMED %s", hx)
            return Fill(True, venue, hx, amount_in, amount_out, price, TxStatus.CONFIRMED, trade=trade)
        except Exception as exc:
            log.error("[TX] error: %s", exc)
            return Fill(False, venue, None, amount_in, Decimal("0"), price, TxStatus.FAILED, str(exc), trade)

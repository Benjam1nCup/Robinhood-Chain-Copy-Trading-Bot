"""Decode swap trades from transaction receipts and calldata."""

from __future__ import annotations

import logging
from typing import Any

from bot.chain import Chain
from bot.config import AppConfig
from bot.constants import KNOWN_ROUTERS, SELECTOR_EXACT_INPUT_SINGLE, TRANSFER_TOPIC, USDG, WETH
from bot.decoder.erc20 import token_meta
from bot.models import RawTransaction, SwapTrade, TradeSide

log = logging.getLogger("rh_copy")


def _topic_addr(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def _parse_transfers(receipt: dict, wallet: str) -> list[dict[str, Any]]:
    wallet = wallet.lower()
    out: list[dict[str, Any]] = []
    for log_entry in receipt.get("logs") or []:
        topics = log_entry.get("topics") or []
        if not topics:
            continue
        t0 = topics[0].hex() if hasattr(topics[0], "hex") else str(topics[0])
        if t0.lower() != TRANSFER_TOPIC.lower():
            continue
        if len(topics) < 3:
            continue
        frm = _topic_addr(topics[1].hex() if hasattr(topics[1], "hex") else str(topics[1]))
        to = _topic_addr(topics[2].hex() if hasattr(topics[2], "hex") else str(topics[2]))
        data = log_entry.get("data") or b""
        raw = int.from_bytes(data if isinstance(data, bytes) else bytes.fromhex(data[2:] if str(data).startswith("0x") else str(data)), "big")
        token = (log_entry.get("address") or "").lower()
        if not token:
            continue
        out.append({"token": token, "from": frm, "to": to, "amount": raw})
    return out


def _classify_side(wallet: str, token_in: str, token_out: str, cfg: AppConfig) -> TradeSide:
    usdg = cfg.uniswap.usdg.lower()
    weth = cfg.uniswap.weth.lower()
    if token_in in {usdg, weth} and token_out not in {usdg, weth}:
        return TradeSide.BUY
    if token_out in {usdg, weth} and token_in not in {usdg, weth}:
        return TradeSide.SELL
    return TradeSide.SWAP


class SwapDecoder:
    def __init__(self, chain: Chain, cfg: AppConfig, token_registry: Any) -> None:
        self.chain = chain
        self.cfg = cfg
        self.registry = token_registry
        routers = set(KNOWN_ROUTERS)
        routers.add(cfg.uniswap.swap_router_02.lower())
        routers.add(cfg.uniswap.universal_router.lower())
        for r in cfg.copy_settings.router_whitelist:
            routers.add(r.lower())
        self.routers = routers

    def decode(self, raw: RawTransaction) -> SwapTrade | None:
        receipt = None
        for _ in range(self.cfg.monitor.max_receipt_retries):
            receipt = self.chain.get_receipt(raw.tx_hash)
            if receipt:
                break
        if not receipt or int(receipt.get("status", 0)) != 1:
            return None

        router = raw.to_address.lower()
        is_router = router in self.routers
        transfers = _parse_transfers(receipt, raw.from_address)
        if not transfers:
            return None

        wallet = raw.from_address.lower()
        sent: dict[str, int] = {}
        recv: dict[str, int] = {}
        for t in transfers:
            if t["from"] == wallet:
                sent[t["token"]] = sent.get(t["token"], 0) + t["amount"]
            if t["to"] == wallet:
                recv[t["token"]] = recv.get(t["token"], 0) + t["amount"]

        token_in, amount_in = "", 0
        token_out, amount_out = "", 0
        for tok, amt in sent.items():
            if amt > amount_in:
                token_in, amount_in = tok, amt
        for tok, amt in recv.items():
            if amt > amount_out:
                token_out, amount_out = tok, amt

        if not token_in or not token_out or token_in == token_out:
            return None
        if self.cfg.copy_settings.only_swaps and not is_router and len(transfers) < 2:
            return None

        sym_in, _, dec_in = token_meta(self.chain, token_in)
        sym_out, _, dec_out = token_meta(self.chain, token_out)
        side = _classify_side(wallet, token_in, token_out, self.cfg)

        fee_tier = self._decode_fee(raw.input_data)
        official_in = self.registry.is_official(token_in)
        official_out = self.registry.is_official(token_out)

        return SwapTrade(
            wallet=wallet,
            tx_hash=raw.tx_hash,
            block_number=raw.block_number,
            timestamp=raw.timestamp,
            router=router,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            amount_out=amount_out,
            decimals_in=dec_in,
            decimals_out=dec_out,
            symbol_in=sym_in,
            symbol_out=sym_out,
            side=side,
            official_in=official_in,
            official_out=official_out,
            fee_tier=fee_tier,
        )

    def _decode_fee(self, input_data: str) -> int | None:
        data = input_data.lower().replace("0x", "")
        if not data.startswith(SELECTOR_EXACT_INPUT_SINGLE):
            return None
        # exactInputSingle params: tokenIn(32) tokenOut(32) fee(32) ...
        if len(data) < 8 + 64 * 3:
            return None
        fee_hex = data[8 + 64 * 2 : 8 + 64 * 3]
        try:
            return int(fee_hex, 16)
        except ValueError:
            return None

"""ERC-20 approval management."""

from __future__ import annotations

import logging

from bot.abis import ERC20_ABI
from bot.chain import Chain
from bot.config import AppConfig
from bot.execution.nonce import NonceManager

log = logging.getLogger("rh_copy")


class ApprovalManager:
    def __init__(self, chain: Chain, cfg: AppConfig, nonce_mgr: NonceManager) -> None:
        self.chain = chain
        self.cfg = cfg
        self.nonce_mgr = nonce_mgr

    def ensure(self, token: str, spender: str, amount: int) -> bool:
        if not self.chain.connected or not self.chain.account:
            return False
        erc = self.chain.contract(token, ERC20_ABI)
        owner = self.chain.checksum(self.chain.address)
        spender_cs = self.chain.checksum(spender)
        current = int(erc.functions.allowance(owner, spender_cs).call())
        if current >= amount:
            return True
        log.info("[APPROVE] %s -> %s", token, spender)
        fn = erc.functions.approve(spender_cs, 2**256 - 1 if self.cfg.execution.approve_once else amount)
        tx = fn.build_transaction(
            {
                "from": self.chain.address,
                "nonce": self.nonce_mgr.next(self.chain.w3, self.chain.address),
                "gas": self.cfg.execution.gas_limit,
                "chainId": self.cfg.chain.chain_id,
            }
        )
        signed = self.chain.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        txh = self.chain.w3.eth.send_raw_transaction(raw)
        rcpt = self.chain.w3.eth.wait_for_transaction_receipt(txh, timeout=self.cfg.execution.tx_confirm_timeout_s)
        status = int(rcpt.get("status") if isinstance(rcpt, dict) else rcpt.status)
        return status == 1

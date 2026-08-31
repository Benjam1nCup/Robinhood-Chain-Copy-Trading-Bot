"""Web3 connection to Robinhood Chain."""

from __future__ import annotations

import logging
from typing import Any

from web3 import Web3

from bot.config import AppConfig
from bot.constants import EXPLORER_MAINNET, EXPLORER_TESTNET

try:
    from web3.middleware import ExtraDataToPOAMiddleware as _poa
except ImportError:
    from web3.middleware import geth_poa_middleware as _poa

log = logging.getLogger("rh_copy")


class Chain:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.w3: Web3 | None = None
        self.account = None
        self.address: str = cfg.wallet_address

    def connect(self) -> bool:
        timeout = self.cfg.chain.request_timeout_s
        self.w3 = Web3(Web3.HTTPProvider(self.cfg.chain.rpc_url, request_kwargs={"timeout": timeout}))
        try:
            self.w3.middleware_onion.inject(_poa, layer=0)
        except Exception:
            pass
        if not self.w3.is_connected():
            log.error("[CHAIN] unable to connect to %s", self.cfg.chain.rpc_url)
            self.w3 = None
            return False
        chain_id = self.w3.eth.chain_id
        log.info("[CHAIN] connected chain_id=%s block=%s", chain_id, self.w3.eth.block_number)
        if chain_id != self.cfg.chain.chain_id:
            log.error("[CHAIN] expected chain_id=%s got %s", self.cfg.chain.chain_id, chain_id)
            return False
        if self.cfg.private_key:
            key = self.cfg.private_key
            if not key.startswith("0x"):
                key = "0x" + key
            self.account = self.w3.eth.account.from_key(key)
            self.address = self.account.address
            log.info("[CHAIN] wallet %s", self.address)
        elif self.address:
            self.address = self.w3.to_checksum_address(self.address)
        return True

    @property
    def connected(self) -> bool:
        return self.w3 is not None and self.w3.is_connected()

    def checksum(self, addr: str) -> str:
        assert self.w3 is not None
        return self.w3.to_checksum_address(addr)

    def contract(self, address: str, abi: list) -> Any:
        assert self.w3 is not None
        return self.w3.eth.contract(address=self.checksum(address), abi=abi)

    def explorer_tx(self, tx_hash: str) -> str:
        base = EXPLORER_MAINNET if self.cfg.chain.chain_id == 4663 else EXPLORER_TESTNET
        return f"{base}/tx/{tx_hash}"

    def native_balance(self) -> int:
        assert self.w3 is not None
        if not self.address:
            return 0
        return int(self.w3.eth.get_balance(self.checksum(self.address)))

    def get_block(self, number: int) -> dict:
        assert self.w3 is not None
        return dict(self.w3.eth.get_block(number, full_transactions=True))

    def get_receipt(self, tx_hash: str) -> dict | None:
        assert self.w3 is not None
        try:
            return dict(self.w3.eth.get_transaction_receipt(tx_hash))
        except Exception:
            return None

    def get_tx(self, tx_hash: str) -> dict | None:
        assert self.w3 is not None
        try:
            return dict(self.w3.eth.get_transaction(tx_hash))
        except Exception:
            return None

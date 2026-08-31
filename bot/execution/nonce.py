"""Local nonce tracking for rapid submissions."""

from __future__ import annotations

import threading


class NonceManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nonce: int | None = None

    def next(self, w3, address: str) -> int:
        with self._lock:
            onchain = w3.eth.get_transaction_count(w3.to_checksum_address(address), "pending")
            if self._nonce is None or onchain > self._nonce:
                self._nonce = int(onchain)
            n = self._nonce
            self._nonce += 1
            return n

    def reset(self) -> None:
        with self._lock:
            self._nonce = None

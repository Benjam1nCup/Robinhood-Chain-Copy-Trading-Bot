"""ERC-20 metadata helpers."""

from __future__ import annotations

import logging

from bot.abis import ERC20_ABI
from bot.chain import Chain

log = logging.getLogger("rh_copy")

_CACHE: dict[str, tuple[str, str, int]] = {}


def token_meta(chain: Chain, address: str) -> tuple[str, str, int]:
    key = address.lower()
    if key in _CACHE:
        return _CACHE[key]
    symbol, name, decimals = "", "", 18
    try:
        erc = chain.contract(address, ERC20_ABI)
        symbol = str(erc.functions.symbol().call())
        name = str(erc.functions.name().call())
        decimals = int(erc.functions.decimals().call())
    except Exception as exc:
        log.debug("[DECODE] token meta %s: %s", address, exc)
    _CACHE[key] = (symbol, name, decimals)
    return symbol, name, decimals

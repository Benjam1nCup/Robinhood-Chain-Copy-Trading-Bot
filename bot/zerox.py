"""0x Swap API for Robinhood Stock Token RFQ liquidity."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import aiohttp

from bot.config import AppConfig

log = logging.getLogger("rh_copy")


class ZeroXClient:
    def __init__(self, cfg: AppConfig, session: aiohttp.ClientSession) -> None:
        self.cfg = cfg
        self.session = session

    @property
    def enabled(self) -> bool:
        return self.cfg.zerox.enabled and bool(self.cfg.zerox_api_key)

    def _headers(self) -> dict[str, str]:
        return {"0x-api-key": self.cfg.zerox_api_key, "0x-version": "v2", "accept": "application/json"}

    async def quote(
        self,
        *,
        sell_token: str,
        buy_token: str,
        sell_amount: int,
        taker: str,
        slippage_bps: int,
    ) -> dict[str, Any] | None:
        params = {
            "chainId": str(self.cfg.chain.chain_id),
            "sellToken": sell_token,
            "buyToken": buy_token,
            "sellAmount": str(sell_amount),
            "taker": taker,
            "slippageBps": str(slippage_bps),
        }
        url = self.cfg.zerox.base_url.rstrip("/") + self.cfg.zerox.quote_path
        try:
            async with self.session.get(
                url, params=params, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    return None
                if isinstance(body, dict) and body.get("liquidityAvailable") is False:
                    return None
                return body if isinstance(body, dict) else None
        except Exception as exc:
            log.warning("[0X] quote failed: %s", exc)
            return None


def implied_price(quote: dict[str, Any], sell_decimals: int, buy_decimals: int) -> Decimal:
    sell = Decimal(str(quote.get("sellAmount") or "0"))
    buy = Decimal(str(quote.get("buyAmount") or "0"))
    if sell <= 0 or buy <= 0:
        return Decimal("0")
    sell_ui = sell / (Decimal(10) ** sell_decimals)
    buy_ui = buy / (Decimal(10) ** buy_decimals)
    return sell_ui / buy_ui if buy_ui else Decimal("0")

"""Wallet scoring for copy sizing tiers."""

from __future__ import annotations

from bot.config import TargetWallet
from bot.store import Store


def wallet_score(wallet: TargetWallet | None, store: Store) -> float:
    if wallet is None:
        return 0.0
    stats = store.load_wallet_stats()
    row = stats.get(wallet.address.lower(), {})
    configured = float(wallet.score)
    trades = int(row.get("trades", 0))
    wins = int(row.get("wins", 0))
    win_rate = (wins / trades * 100) if trades else configured
    recent = float(row.get("recent_score", configured))
    consistency = float(row.get("consistency", 50))
    liquidity_pref = float(row.get("liquidity_score", 50))

    score = (
        0.30 * configured
        + 0.20 * win_rate
        + 0.20 * liquidity_pref
        + 0.15 * consistency
        + 0.15 * recent
    )
    return min(100.0, max(0.0, score))

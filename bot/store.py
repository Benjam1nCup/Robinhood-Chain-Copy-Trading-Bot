"""JSON persistence for trades, positions, and wallet stats."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("rh_copy")


class Store:
    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.seen_tx_path = self.root / "seen_tx.json"
        self.positions_path = self.root / "positions.json"
        self.trades_path = self.root / "trades.jsonl"
        self.paper_path = self.root / "paper_wallet.json"
        self.wallet_stats_path = self.root / "wallet_stats.json"
        self.daily_pnl_path = self.root / "daily_pnl.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text())
        except Exception as exc:
            log.warning("[STORE] bad json %s: %s", path, exc)
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(path)

    def load_seen_tx(self) -> set[str]:
        data = self._read_json(self.seen_tx_path, {"hashes": []})
        return set(str(x).lower() for x in data.get("hashes", []))

    def save_seen_tx(self, hashes: set[str]) -> None:
        self._write_json(self.seen_tx_path, {"hashes": sorted(hashes)})

    def mark_seen(self, tx_hash: str, seen: set[str]) -> None:
        seen.add(tx_hash.lower())
        if len(seen) % 50 == 0:
            self.save_seen_tx(seen)

    def load_positions(self) -> list[dict[str, Any]]:
        data = self._read_json(self.positions_path, {"positions": []})
        return list(data.get("positions") or [])

    def save_positions(self, rows: list[dict[str, Any]]) -> None:
        self._write_json(self.positions_path, {"positions": rows})

    def append_trade(self, row: dict[str, Any]) -> None:
        with self.trades_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def load_paper_wallet(self) -> dict[str, Any]:
        return self._read_json(self.paper_path, {"usdg": "5000", "tokens": {}})

    def save_paper_wallet(self, payload: dict[str, Any]) -> None:
        self._write_json(self.paper_path, payload)

    def load_wallet_stats(self) -> dict[str, Any]:
        return self._read_json(self.wallet_stats_path, {})

    def save_wallet_stats(self, stats: dict[str, Any]) -> None:
        self._write_json(self.wallet_stats_path, stats)

    def load_daily_pnl(self) -> dict[str, Any]:
        return self._read_json(self.daily_pnl_path, {"date": "", "realized_loss_usd": 0})

    def save_daily_pnl(self, payload: dict[str, Any]) -> None:
        self._write_json(self.daily_pnl_path, payload)

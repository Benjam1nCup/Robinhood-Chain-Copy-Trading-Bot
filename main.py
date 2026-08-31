"""CLI entrypoint for the Robinhood Chain Copy Trading Bot."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from bot.config import load_config
from bot.logging_setup import setup_logging


def _cfg(args):
    return load_config(args.config)


async def cmd_run(args) -> int:
    cfg = _cfg(args)
    if args.paper:
        cfg.bot.paper_trading = True
    if args.live:
        cfg.bot.paper_trading = False
        cfg.bot.dry_run = False
    from bot.engine import CopyTradingEngine

    engine = CopyTradingEngine(cfg)
    try:
        await engine.start()
    except KeyboardInterrupt:
        pass
    finally:
        await engine.close()
    return 0


async def cmd_catalog(args) -> int:
    cfg = _cfg(args)
    setup_logging(cfg.bot.log_level, "", False)
    import aiohttp

    from bot.data.tokens import TokenRegistry, normalize_symbol, chain_deployment

    async with aiohttp.ClientSession() as session:
        reg = TokenRegistry(cfg, session)
        await reg.refresh(force=True)
        assets = list(reg.by_symbol.values())
    rows = []
    for a in assets:
        dep = chain_deployment(a, cfg.chain.chain_id)
        rows.append(
            {
                "symbol": normalize_symbol(a.get("tokenSymbol") or ""),
                "address": (dep or {}).get("contractAddress"),
                "multiplier": a.get("currentMultiplier"),
                "status": a.get("status"),
            }
        )
    rows.sort(key=lambda r: r["symbol"])
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{len(rows)} Stock Tokens on chain {cfg.chain.chain_id}")
        for r in rows:
            print(f"  {r['symbol']:<8} {r['address']}  {r['status']}")
    return 0


async def cmd_wallets(args) -> int:
    cfg = _cfg(args)
    for w in cfg.target_wallets:
        flag = "ON" if w.enabled else "OFF"
        print(f"  [{flag}] {w.address}  label={w.label}  score={w.score}  max=${w.max_position_usd or cfg.copy_settings.max_position_usd}")
    return 0


def cmd_connect(args) -> int:
    cfg = _cfg(args)
    setup_logging(cfg.bot.log_level, "", False)
    from bot.chain import Chain

    return 0 if Chain(cfg).connect() else 1


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Robinhood Chain Copy Trading Bot")
    p.add_argument("--config", default=str(root / "config" / "default.yaml"))
    p.add_argument("--paper", action="store_true", help="force paper trading")
    p.add_argument("--live", action="store_true", help="attempt live mode (needs CONFIRM_LIVE_TRADING=YES)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("run", help="run the copy bot (default)")
    sub.add_parser("wallets", help="list configured target wallets")

    cat = sub.add_parser("catalog", help="list official Stock Tokens")
    cat.add_argument("--json", action="store_true")

    sub.add_parser("connect", help="verify RPC + chain id")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.cmd or "run"
    if cmd == "run":
        return asyncio.run(cmd_run(args))
    if cmd == "catalog":
        return asyncio.run(cmd_catalog(args))
    if cmd == "wallets":
        return asyncio.run(cmd_wallets(args))
    if cmd == "connect":
        return cmd_connect(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

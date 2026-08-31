"""YAML + environment configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class BotCfg(BaseModel):
    dry_run: bool = True
    paper_trading: bool = True
    paper_starting_usdg: float = 5000.0
    paper_fee_bps: float = 5.0
    log_level: str = "INFO"
    log_file: str = "logs/copybot.log"
    log_timestamp_name: bool = True
    heartbeat_s: float = 30.0
    stop_trading: bool = False


class ChainCfg(BaseModel):
    chain_id: int = 4663
    rpc_url: str = "https://rpc.mainnet.chain.robinhood.com"
    ws_url: str = ""
    sequencer_feed: str = "wss://feed.mainnet.chain.robinhood.com"
    request_timeout_s: float = 20.0
    poll_blocks_s: float = 2.0
    data_streams_verifier: str = "0xcE73c8ad08CBDEaCa6078BF0627C8fe0a9a536E7"


class StockTokenCfg(BaseModel):
    assets_url: str = "https://api.robinhood.com/rhj/assets"
    prices_url: str = "https://api.robinhood.com/rhj/prices"
    corporate_actions_url: str = "https://api.robinhood.com/rhj/corporate-actions"
    refresh_interval_s: float = 300.0


class UniswapCfg(BaseModel):
    v3_factory: str = "0x1f7d7550B1b028f7571E69A784071F0205FD2EfA"
    swap_router_02: str = "0xCaf681a66D020601342297493863E78C959E5cb2"
    quoter_v2: str = "0x33e885eD0Ec9bF04EcfB19341582aADCb4c8A9E7"
    universal_router: str = "0x8876789976dEcBfCbBbe364623C63652db8C0904"
    permit2: str = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
    weth: str = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
    usdg: str = "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168"
    fee_tiers: list[int] = Field(default_factory=lambda: [100, 500, 3000, 10000])


class ZeroXCfg(BaseModel):
    enabled: bool = True
    base_url: str = "https://api.0x.org"
    quote_path: str = "/swap/allowance-holder/quote"
    price_path: str = "/swap/allowance-holder/price"


class CopyCfg(BaseModel):
    model_config = {"populate_by_name": True}

    sizing_mode: str = "hybrid"
    copy_ratio: float = 0.10
    fixed_size_usd: float = 100.0
    max_position_usd: float = 500.0
    min_position_usd: float = 10.0
    max_trade_age_s: float = 30.0
    max_slippage_bps: int = 100
    min_liquidity_usd: float = 50_000.0
    max_liquidity_ratio: float = 0.05
    require_official_token: bool = False
    copy_exits: bool = True
    only_swaps: bool = True
    min_gas_balance_eth: float = 0.001
    max_daily_loss_usd: float = 250.0
    max_token_exposure_usd: float = 1000.0
    token_blacklist: list[str] = Field(default_factory=list)
    router_whitelist: list[str] = Field(default_factory=list)


class RiskCfg(BaseModel):
    reject_trading_halt: bool = True
    reject_unknown_tokens: bool = False
    min_wallet_score: float = 40.0
    emergency_stop_file: str = "data/STOP"


class ExecutionCfg(BaseModel):
    gas_limit: int = 400_000
    tx_confirm_timeout_s: float = 90.0
    approve_once: bool = True
    prefer_zerox_for_official: bool = True


class MonitorCfg(BaseModel):
    mode: str = "blocks"
    start_block: str = "latest"
    max_receipt_retries: int = 3


class TargetWallet(BaseModel):
    address: str
    enabled: bool = True
    label: str = ""
    max_position_usd: float | None = None
    copy_ratio: float | None = None
    score: float = 50.0


class AppConfig(BaseModel):
    model_config = {"populate_by_name": True}

    bot: BotCfg = BotCfg()
    chain: ChainCfg = ChainCfg()
    stock_tokens: StockTokenCfg = StockTokenCfg()
    uniswap: UniswapCfg = UniswapCfg()
    zerox: ZeroXCfg = ZeroXCfg()
    copy_settings: CopyCfg = Field(default_factory=CopyCfg, alias="copy")
    risk: RiskCfg = RiskCfg()
    execution: ExecutionCfg = ExecutionCfg()
    monitor: MonitorCfg = MonitorCfg()
    wallets_file: str = "config/wallets.json"
    private_key: str = ""
    wallet_address: str = ""
    zerox_api_key: str = ""
    confirm_live_trading: str = "NO"
    target_wallets: list[TargetWallet] = Field(default_factory=list)

    @property
    def live_enabled(self) -> bool:
        return (
            not self.bot.dry_run
            and not self.bot.paper_trading
            and bool(self.private_key)
            and self.confirm_live_trading.strip().upper() == "YES"
        )

    def enabled_wallets(self) -> list[TargetWallet]:
        return [w for w in self.target_wallets if w.enabled]

    def wallet_map(self) -> dict[str, TargetWallet]:
        return {w.address.lower(): w for w in self.target_wallets}


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_wallets(path: Path) -> list[TargetWallet]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    rows = data.get("wallets") if isinstance(data, dict) else data
    out: list[TargetWallet] = []
    for row in rows or []:
        addr = str(row.get("address") or "").strip()
        if not addr:
            continue
        out.append(TargetWallet.model_validate(row))
    return out


def load_config(path: str | Path | None = None) -> AppConfig:
    load_dotenv()
    root = Path(__file__).resolve().parents[1]
    cfg_path = Path(path) if path else root / "config" / "default.yaml"
    raw: dict = {}
    if cfg_path.exists():
        with cfg_path.open() as f:
            raw = yaml.safe_load(f) or {}
    cfg = AppConfig.model_validate(raw)

    wallets_path = root / cfg.wallets_file
    if not wallets_path.is_absolute():
        wallets_path = root / cfg.wallets_file
    cfg.target_wallets = load_wallets(wallets_path)

    if os.getenv("RH_RPC_URL"):
        cfg.chain.rpc_url = os.environ["RH_RPC_URL"]
    if os.getenv("RH_WS_URL"):
        cfg.chain.ws_url = os.environ["RH_WS_URL"]
    cfg.private_key = os.getenv("PRIVATE_KEY", cfg.private_key)
    cfg.wallet_address = os.getenv("WALLET_ADDRESS", cfg.wallet_address)
    cfg.zerox_api_key = os.getenv("ZEROX_API_KEY", cfg.zerox_api_key)
    cfg.confirm_live_trading = os.getenv("CONFIRM_LIVE_TRADING", cfg.confirm_live_trading)
    cfg.bot.dry_run = _as_bool(os.getenv("DRY_RUN"), cfg.bot.dry_run)
    cfg.bot.paper_trading = _as_bool(os.getenv("PAPER_TRADING"), cfg.bot.paper_trading)
    cfg.bot.stop_trading = _as_bool(os.getenv("STOP_TRADING"), cfg.bot.stop_trading)
    return cfg

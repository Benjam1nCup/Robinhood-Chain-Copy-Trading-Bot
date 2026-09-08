# Robinhood Chain Copy Trading Bot

Automatically monitor target wallets on [Robinhood Chain](https://docs.robinhood.com/chain/), detect DEX swaps, apply risk rules, and execute proportional copy trades from your own wallet.


If you want other types of Robin Hood chain bots, you can find other bots in this repository.

[https://github.com/Benjam1nCup/Robinhood-Trading-Bot-System](https://github.com/Benjam1nCup/Robinhood-Trading-Bot-System)


## Architecture

```text
Target Wallets → Block Monitor → Swap Decoder → Copy Strategy → Risk Engine → Executor → Portfolio
                      ↑                              ↑
              Token Registry (RHJ API)        Price Service
```

## Features

- **Wallet monitoring** — polls new blocks for transactions from configured target wallets
- **Swap detection** — decodes Uniswap v3 / router swaps via receipt Transfer events
- **Stock Token registry** — loads canonical addresses from [RHJ `/assets` API](https://docs.robinhood.com/chain/stock-token-apis/)
- **Position sizing** — proportional, fixed, or hybrid with per-wallet caps
- **Risk controls** — slippage limits, trade age, liquidity ratio, daily loss, emergency stop
- **Exit copying** — proportional sell when target wallet exits
- **Execution** — 0x RFQ for official tokens, Uniswap v3 fallback
- **Paper trading** — simulate fills without broadcasting transactions

## Quick Start

```bash
cd /root/Jipred/Robinhood-Chain-Copy-Trading-Bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Configure target wallets

Edit `config/wallets.json`:

```json
{
  "wallets": [
    {
      "address": "0xYourTargetWallet...",
      "enabled": true,
      "label": "alpha-trader",
      "max_position_usd": 500,
      "copy_ratio": 0.10,
      "score": 75
    }
  ]
}
```

### Run (paper mode — default)

```bash
python main.py run
```

### Verify RPC connection

```bash
python main.py connect
```

### List official Stock Tokens

```bash
python main.py catalog
```

## Configuration

| File | Purpose |
|------|---------|
| `config/default.yaml` | Chain, copy sizing, risk, execution settings |
| `config/wallets.json` | Target wallets with per-wallet limits |
| `.env` | RPC URL, private key, API keys, safety gates |

### Live trading gates

All three must be set for real transactions:

```bash
DRY_RUN=false
PAPER_TRADING=false
CONFIRM_LIVE_TRADING=YES
PRIVATE_KEY=0x...
ZEROX_API_KEY=...   # recommended for Stock Token RFQ
```

### Emergency stop

```bash
# Option 1: environment variable
export STOP_TRADING=true

# Option 2: touch stop file
touch data/STOP
```

## Network

| Property | Mainnet | Testnet |
|----------|---------|---------|
| Chain ID | 4663 | 46630 |
| Public RPC | `https://rpc.mainnet.chain.robinhood.com` | `https://rpc.testnet.chain.robinhood.com` |
| Sequencer Feed | `wss://feed.mainnet.chain.robinhood.com` | `wss://feed.testnet.chain.robinhood.com` |

For production, use [Alchemy](https://docs.robinhood.com/chain/connecting/) or another provider.

## Project Structure

```text
bot/
  monitor/       # Block polling, wallet tracking
  decoder/       # Swap classification from receipts
  strategy/      # Filters, sizing, risk, wallet scoring
  execution/     # Nonce, approvals, gas, swap broadcast
  portfolio/     # Position tracking, PnL
  data/          # RHJ token registry + prices
  engine.py      # Main event loop
config/
  default.yaml
  wallets.json
main.py
```

## Tests

```bash
pytest tests/ -q
```

## Docs

- [Robinhood Chain](https://docs.robinhood.com/chain/)
- [Connecting](https://docs.robinhood.com/chain/connecting/)
- [Stock Token APIs](https://docs.robinhood.com/chain/stock-token-apis/)
- [Data Streams](https://docs.robinhood.com/chain/data-streams/)
- [Deploy Smart Contracts](https://docs.robinhood.com/chain/deploy-smart-contracts/)

## Disclaimer

This software is for educational purposes. Copy trading carries significant financial risk. Test thoroughly on testnet before using real funds. Never commit private keys.

"""Network constants for Robinhood Chain (mainnet 4663 / testnet 46630)."""

from __future__ import annotations

MAINNET_CHAIN_ID = 4663
TESTNET_CHAIN_ID = 46630

PUBLIC_RPC_MAINNET = "https://rpc.mainnet.chain.robinhood.com"
PUBLIC_RPC_TESTNET = "https://rpc.testnet.chain.robinhood.com"
PUBLIC_WS_MAINNET = "wss://feed.mainnet.chain.robinhood.com"
EXPLORER_MAINNET = "https://robinhoodchain.blockscout.com"
EXPLORER_TESTNET = "https://explorer.testnet.chain.robinhood.com"

WETH = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
USDG = "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168"
USDG_DECIMALS = 6
WETH_DECIMALS = 18
NATIVE_ETH = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

UNI_V3_FACTORY = "0x1f7d7550B1b028f7571E69A784071F0205FD2EfA"
SWAP_ROUTER_02 = "0xCaf681a66D020601342297493863E78C959E5cb2"
QUOTER_V2 = "0x33e885eD0Ec9bF04EcfB19341582aADCb4c8A9E7"
UNIVERSAL_ROUTER = "0x8876789976dEcBfCbBbe364623C63652db8C0904"
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

RHJ_ASSETS_URL = "https://api.robinhood.com/rhj/assets"
RHJ_PRICES_URL = "https://api.robinhood.com/rhj/prices"

# ERC-20 Transfer(address,address,uint256)
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Known swap routers on Robinhood Chain
KNOWN_ROUTERS = {
    SWAP_ROUTER_02.lower(),
    UNIVERSAL_ROUTER.lower(),
}

# exactInputSingle selector
SELECTOR_EXACT_INPUT_SINGLE = "414bf389"

"""Competitor registry — single source of truth for all tracked protocols."""

import os
import streamlit as st


def get_secret(key: str) -> str | None:
    """Streamlit Cloud uses st.secrets, local dev uses env vars."""
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key)


# Dune query IDs — replace with actual IDs after creating queries on dune.com
DUNE_QUERIES = {
    "holders": 6785925,           # Query 1: ERC-20 holder counts
    "active_addresses": 6785945,  # Query 2: Daily active addresses (30d)
    "bridge_volume": 6785963,     # Query 3: Bridge/mint volume (30d)
}

COMPETITORS = [
    # ===== Cluster 1: CeFi Bitcoin Lending =====
    {"name": "Nexo", "cluster": 1, "cluster_name": "CeFi Bitcoin Lending",
     "defillama_slug": None, "aave_symbol": None,
     "website": "nexo.com/borrow/bitcoin", "token_contract": None, "dune_token_address": None},
    {"name": "Ledn", "cluster": 1, "cluster_name": "CeFi Bitcoin Lending",
     "defillama_slug": None, "aave_symbol": None,
     "website": "ledn.io", "token_contract": None, "dune_token_address": None},
    {"name": "Xapo Bank", "cluster": 1, "cluster_name": "CeFi Bitcoin Lending",
     "defillama_slug": None, "aave_symbol": None,
     "website": "xapobank.com", "token_contract": None, "dune_token_address": None},
    {"name": "Lygos Finance", "cluster": 1, "cluster_name": "CeFi Bitcoin Lending",
     "defillama_slug": None, "aave_symbol": None,
     "website": "lygos.finance", "token_contract": None, "dune_token_address": None},
    {"name": "Two Prime", "cluster": 1, "cluster_name": "CeFi Bitcoin Lending",
     "defillama_slug": None, "aave_symbol": None,
     "website": "twoprime.com", "token_contract": None, "dune_token_address": None},
    {"name": "Bitcoin Suisse", "cluster": 1, "cluster_name": "CeFi Bitcoin Lending",
     "defillama_slug": None, "aave_symbol": None,
     "website": "bitcoinsuisse.com", "token_contract": None, "dune_token_address": None},
    {"name": "SatsTerminal", "cluster": 1, "cluster_name": "CeFi Bitcoin Lending",
     "defillama_slug": None, "aave_symbol": None,
     "website": "borrow.satsterminal.com", "token_contract": None, "dune_token_address": None},

    # ===== Cluster 2: Centralized Wrapped BTC =====
    {"name": "wBTC", "cluster": 2, "cluster_name": "Centralized Wrapped BTC",
     "defillama_slug": "wbtc", "aave_symbol": "WBTC",
     "website": "wbtc.network", "token_contract": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
     "dune_token_address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"},
    {"name": "cbBTC", "cluster": 2, "cluster_name": "Centralized Wrapped BTC",
     "defillama_slug": None, "aave_symbol": "cbBTC",
     "coingecko_id": "coinbase-wrapped-btc",
     "website": "coinbase.com", "token_contract": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",
     "dune_token_address": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"},

    # ===== Cluster 3: Trust-Minimized BTC & LSTs =====
    {"name": "tBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "tbtc", "aave_symbol": "tBTC",
     "website": "threshold.network", "token_contract": "0x18084fbA666a33d37592fA2633fD49a74DD93a88",
     "dune_token_address": "0x18084fbA666a33d37592fA2633fD49a74DD93a88"},
    {"name": "LBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "lombard", "aave_symbol": "LBTC",
     "website": "lombard.finance", "token_contract": "0x8236a87084f8B84306f72007F36F2618A5634494",
     "dune_token_address": "0x8236a87084f8B84306f72007F36F2618A5634494"},
    {"name": "SolvBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "solv-protocol", "aave_symbol": None,
     "website": "solv.finance", "token_contract": "0x7A56E1C57C7475CCf65CfbCd7E7c62F694d313A4",
     "dune_token_address": "0x7A56E1C57C7475CCf65CfbCd7E7c62F694d313A4"},
    {"name": "FBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "fbtc", "aave_symbol": None,
     "website": "fbtc.com", "token_contract": None, "dune_token_address": None},
    {"name": "uniBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "bedrock", "aave_symbol": None,
     "website": "bedrock.technology", "token_contract": None, "dune_token_address": None},
    {"name": "eBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "ebtc", "aave_symbol": None,
     "website": "ebtc.finance", "token_contract": None, "dune_token_address": None},
    {"name": "pumpBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "pumpbtc", "aave_symbol": None,
     "website": "pumpbtc.xyz", "token_contract": None, "dune_token_address": None},
    {"name": "sBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "stacks", "aave_symbol": None,
     "website": "stacks.co", "token_contract": None, "dune_token_address": None},
    {"name": "Lorenzo stBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "lorenzo-protocol", "aave_symbol": None,
     "website": "lorenzo-protocol.xyz", "token_contract": None, "dune_token_address": None},
    {"name": "coreBTC", "cluster": 3, "cluster_name": "Trust-Minimized BTC & LSTs",
     "defillama_slug": "core-dao", "aave_symbol": None,
     "website": "coredao.org", "token_contract": None, "dune_token_address": None},

    # ===== Cluster 4: Bitcoin L2 & Infrastructure =====
    {"name": "BOB", "cluster": 4, "cluster_name": "Bitcoin L2 & Infrastructure",
     "defillama_slug": "bob-fusion", "aave_symbol": None,
     "website": "gobob.xyz", "token_contract": None, "dune_token_address": None},
    {"name": "BitLayer", "cluster": 4, "cluster_name": "Bitcoin L2 & Infrastructure",
     "defillama_slug": "bitlayer", "aave_symbol": None,
     "website": "bitlayer.org", "token_contract": None, "dune_token_address": None},
    {"name": "Citrea", "cluster": 4, "cluster_name": "Bitcoin L2 & Infrastructure",
     "defillama_slug": "citrea", "aave_symbol": None,
     "website": "citrea.xyz", "token_contract": None, "dune_token_address": None},
    {"name": "Stacks", "cluster": 4, "cluster_name": "Bitcoin L2 & Infrastructure",
     "defillama_slug": "stacks", "aave_symbol": None,
     "website": "stacks.co", "token_contract": None, "dune_token_address": None},
    {"name": "Core Chain", "cluster": 4, "cluster_name": "Bitcoin L2 & Infrastructure",
     "defillama_slug": "core", "aave_symbol": None,
     "website": "coredao.org", "token_contract": None, "dune_token_address": None},
    {"name": "Mezo", "cluster": 4, "cluster_name": "Bitcoin L2 & Infrastructure",
     "defillama_slug": "mezo", "aave_symbol": None,
     "website": "mezo.org", "token_contract": None, "dune_token_address": None},
]

CLUSTER_NAMES = {
    1: "CeFi Bitcoin Lending",
    2: "Centralized Wrapped BTC",
    3: "Trust-Minimized BTC & LSTs",
    4: "Bitcoin L2 & Infrastructure",
}

CLUSTER_COLORS = {
    1: "#FF6B6B",
    2: "#4ECDC4",
    3: "#F7931A",
    4: "#7B68EE",
}

TBV_LAUNCH_TARGET = "2026-06-30"  # Q2 2026

"""Fetch DeFi integration data from DeFi Llama yields API. Free, no key.

Methodology:
  1. Fetch all yield pools from DeFi Llama
  2. For each BTC asset, find pools containing that token via EXACT token match
     (pool symbol split by separators, case-insensitive comparison)
  3. Filter out dead pools (TVL < $10k)
  4. Count unique DeFi protocols (projects) = "integrations"
  5. Count unique chains = "chain diversity"
"""

import requests
import pandas as pd

YIELDS_URL = "https://yields.llama.fi/pools"
TIMEOUT = 15

# Minimum pool TVL to count as active integration (filters dead/dust pools)
MIN_POOL_TVL = 10_000  # $10k

# Map competitor names to token symbols to search in yield pools
SYMBOL_MAP = {
    "wBTC": ["WBTC"],
    "cbBTC": ["CBBTC"],
    "tBTC": ["TBTC"],
    "LBTC": ["LBTC"],
    "SolvBTC": ["SOLVBTC", "SOLVBTC.BBN"],
    "pumpBTC": ["PUMPBTC"],
    "sBTC": ["SBTC"],
    "uniBTC": ["UNIBTC"],
    "eBTC": ["EBTC"],
    "FBTC": ["FBTC"],
    "coreBTC": ["COREBTC"],
    "Lorenzo stBTC": ["STBTC"],
}


def _tokenize_pool_symbol(symbol: str) -> set[str]:
    """Split pool symbol into individual token names.

    Handles separators: - / + _ and space.
    E.g. "WBTC-USDC" -> {"WBTC", "USDC"}
         "cbBTC/ETH" -> {"CBBTC", "ETH"}
    """
    normalized = symbol.upper()
    for sep in ["-", "/", "+", "_"]:
        normalized = normalized.replace(sep, " ")
    return {t.strip() for t in normalized.split() if t.strip()}


def _pool_matches(pool_symbol: str, target_symbols: list[str]) -> bool:
    """Check if pool contains one of target tokens via exact token-level match."""
    pool_tokens = _tokenize_pool_symbol(pool_symbol)
    return any(s in pool_tokens for s in target_symbols)


def fetch_defi_yields() -> pd.DataFrame:
    """Fetch yield pools and count DeFi integrations per BTC asset.

    Returns DataFrame with columns:
        name, defi_integrations_count, total_pool_tvl, top_integrations,
        chain_count, active_pool_count
    """
    resp = requests.get(YIELDS_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    pools = resp.json().get("data", [])

    rows = []
    for name, symbols in SYMBOL_MAP.items():
        # Exact token-level matching
        matching = [
            p for p in pools
            if _pool_matches(p.get("symbol", ""), symbols)
        ]

        # Filter active pools only (TVL > threshold)
        active = [
            p for p in matching
            if (p.get("tvlUsd", 0) or 0) >= MIN_POOL_TVL
        ]

        if not active:
            rows.append({
                "name": name,
                "defi_integrations_count": 0,
                "total_pool_tvl": 0,
                "top_integrations": [],
                "chain_count": 0,
                "active_pool_count": 0,
            })
            continue

        # Count unique projects (= integrations)
        projects: dict[str, float] = {}
        chains: set[str] = set()
        for pool in active:
            proj = pool.get("project", "unknown")
            tvl = pool.get("tvlUsd", 0) or 0
            projects[proj] = projects.get(proj, 0) + tvl
            chains.add(pool.get("chain", "unknown"))

        # Sort by TVL
        sorted_projects = sorted(projects.items(), key=lambda x: x[1], reverse=True)

        rows.append({
            "name": name,
            "defi_integrations_count": len(projects),
            "total_pool_tvl": sum(p.get("tvlUsd", 0) or 0 for p in active),
            "top_integrations": [p[0] for p in sorted_projects[:5]],
            "chain_count": len(chains),
            "active_pool_count": len(active),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_defi_yields_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_defi_yields()
    except Exception as e:
        print(f"DeFi yields fetch failed: {e}")
        return pd.DataFrame()

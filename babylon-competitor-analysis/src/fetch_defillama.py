"""Fetch TVL data from DeFi Llama. Free, no API key needed."""

import time
import requests
import pandas as pd

BASE_URL = "https://api.llama.fi"
TIMEOUT = 10
MAX_RETRIES = 3


def _get(url: str) -> dict | list | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None


def fetch_defillama(slugs: list[str]) -> pd.DataFrame:
    """Fetch TVL data for given DeFi Llama slugs.

    Returns DataFrame with columns:
        name, defillama_slug, tvl_usd, tvl_change_7d_pct, tvl_change_30d_pct,
        chains_count, mcap, tvl_history
    """
    rows = []

    for slug in slugs:
        if not slug:
            continue

        data = _get(f"{BASE_URL}/protocol/{slug}")
        if not data:
            continue

        tvl_history = []
        chain_tvls = data.get("chainTvls", {})
        # Use total TVL history from all chains
        for chain_name, chain_data in chain_tvls.items():
            if chain_name == "borrowed" or "-borrowed" in chain_name:
                continue
            if chain_name == "staking" or "-staking" in chain_name:
                continue

        # Get main TVL history
        tvl_data = data.get("tvl", [])
        if tvl_data:
            tvl_history = [(entry["date"], entry["totalLiquidityUSD"]) for entry in tvl_data[-730:]]

        current_tvl = data.get("currentChainTvls", {})
        total_tvl = sum(
            v for k, v in current_tvl.items()
            if not k.endswith("-borrowed") and not k.endswith("-staking")
            and k != "borrowed" and k != "staking"
        )

        # Calculate TVL changes
        tvl_7d_ago = None
        tvl_30d_ago = None
        now = time.time()
        for date_ts, tvl_val in reversed(tvl_history):
            age_days = (now - date_ts) / 86400
            if tvl_7d_ago is None and age_days >= 7:
                tvl_7d_ago = tvl_val
            if tvl_30d_ago is None and age_days >= 30:
                tvl_30d_ago = tvl_val
                break

        tvl_change_7d = ((total_tvl - tvl_7d_ago) / tvl_7d_ago * 100) if tvl_7d_ago else None
        tvl_change_30d = ((total_tvl - tvl_30d_ago) / tvl_30d_ago * 100) if tvl_30d_ago else None

        chains = [k for k in current_tvl.keys()
                  if not k.endswith("-borrowed") and not k.endswith("-staking")
                  and k != "borrowed" and k != "staking"]

        rows.append({
            "defillama_slug": slug,
            "tvl_usd": total_tvl,
            "tvl_change_7d_pct": round(tvl_change_7d, 2) if tvl_change_7d is not None else None,
            "tvl_change_30d_pct": round(tvl_change_30d, 2) if tvl_change_30d is not None else None,
            "chains_count": len(chains),
            "chains": ", ".join(chains[:10]),
            "mcap": data.get("mcap"),
            "tvl_history": tvl_history,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_defillama_safe(slugs: list[str]) -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_defillama(slugs)
    except Exception as e:
        print(f"DeFi Llama fetch failed: {e}")
        return pd.DataFrame()

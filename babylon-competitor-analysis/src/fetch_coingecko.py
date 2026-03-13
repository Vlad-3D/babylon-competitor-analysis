"""Fetch market cap data from CoinGecko. Free API, no key needed (rate-limited).

Used for tokens like cbBTC that DeFi Llama doesn't track as protocols.
"""

import time
import requests
import pandas as pd

BASE_URL = "https://api.coingecko.com/api/v3"
TIMEOUT = 15
MAX_RETRIES = 3


def _get(url: str) -> dict | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            if resp.status_code == 429:
                # Rate limited — wait and retry
                time.sleep(30)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None


def fetch_coingecko(coin_ids: dict[str, str]) -> pd.DataFrame:
    """Fetch market data for given CoinGecko coin IDs.

    Args:
        coin_ids: mapping of competitor name → CoinGecko coin ID
                  e.g. {"cbBTC": "coinbase-wrapped-btc"}

    Returns DataFrame with columns:
        name, coingecko_mcap, coingecko_price, coingecko_circulating_supply,
        coingecko_change_24h_pct
    """
    rows = []

    for name, coin_id in coin_ids.items():
        if not coin_id:
            continue

        data = _get(f"{BASE_URL}/coins/{coin_id}")
        if not data:
            print(f"  CoinGecko: no data for {coin_id}")
            continue

        market = data.get("market_data", {})

        mcap = market.get("market_cap", {}).get("usd")
        price = market.get("current_price", {}).get("usd")
        circulating = market.get("circulating_supply")
        change_24h = market.get("price_change_percentage_24h")

        rows.append({
            "name": name,
            "coingecko_mcap": mcap,
            "coingecko_price": price,
            "coingecko_circulating_supply": circulating,
            "coingecko_change_24h_pct": round(change_24h, 2) if change_24h is not None else None,
        })

        # CoinGecko free API: ~10-30 req/min — small delay between calls
        time.sleep(2)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_coingecko_safe(coin_ids: dict[str, str]) -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_coingecko(coin_ids)
    except Exception as e:
        print(f"CoinGecko fetch failed: {e}")
        return pd.DataFrame()

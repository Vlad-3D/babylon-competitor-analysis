"""Fetch Aave V3 USDC/USDT borrow rates on Ethereum + Base — weekly, 2 years.

These are the rates borrowers pay when taking USDC/USDT loans against BTC collateral
(wBTC, cbBTC). Aave V3 uses pooled rates — the borrow rate is the same regardless of
collateral type, so the USDC/USDT pool borrow rate IS the rate for BTC-collateral borrowers.

Data source: The Graph — reserveParamsHistoryItems (variableBorrowRate in RAY).
BTC price: DeFi Llama coins chart API.

Speed: Uses batched GraphQL queries (10 weeks per request) — ~30 queries instead of ~300.
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

from src.config import get_secret

TIMEOUT = 20
RAY = 1e27
WEEKS = 104  # 2 years
BATCH_SIZE = 10  # weeks per GraphQL request

# Aave V3 subgraph IDs
SUBGRAPHS = {
    "ethereum": "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g",
    "base": "GQFbb95cE6d8mV989mL5figjaGaKCQB3xqYrr1bRyXqF",
}

# Reserve IDs: token address + pool address (Aave V3 format)
RESERVES = {
    "ethereum": {
        "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480x2f39d218133afab8f2b819b1066c7e434ad94e9e",
        "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec70x2f39d218133afab8f2b819b1066c7e434ad94e9e",
    },
    "base": {
        "USDC": "0x833589fcd6edb6e08f4c7c32d4f71b54bda029130xe20fcbdbffc4dd138ce8b2e6fbb6cb49777ad64d",
        # No USDT on Aave V3 Base
    },
}


def _graph_url(chain: str) -> str | None:
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return None
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{SUBGRAPHS[chain]}"


def _query_graph(url: str, query: str) -> dict | None:
    for attempt in range(3):
        try:
            resp = requests.post(url, json={"query": query}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                print(f"    Graph errors: {data['errors'][:200]}")
                return None
            return data.get("data")
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"    Graph request failed: {e}")
    return None


def _batch_weekly_snapshots(
    url: str, reserve_id: str, timestamps: list[int]
) -> dict[int, dict]:
    """Fetch multiple weekly snapshots in one GraphQL request using aliases.

    Returns {timestamp: {variableBorrowRate, utilizationRate}} for each found week.
    """
    # Build aliased query — one alias per week
    parts = []
    for i, ts in enumerate(timestamps):
        parts.append(
            f'w{i}: reserveParamsHistoryItems('
            f'first: 1, orderBy: timestamp, orderDirection: desc, '
            f'where: {{ reserve: "{reserve_id}", timestamp_lte: {ts} }}'
            f') {{ timestamp variableBorrowRate utilizationRate }}'
        )
    query = "{ " + " ".join(parts) + " }"

    data = _query_graph(url, query)
    if not data:
        return {}

    results = {}
    for i, ts in enumerate(timestamps):
        items = data.get(f"w{i}", [])
        if items:
            results[ts] = items[0]
    return results


def _generate_week_timestamps() -> list[int]:
    """Generate Friday-end-of-day timestamps for last 2 years."""
    now = datetime.now(timezone.utc)
    days_since_friday = (now.weekday() - 4) % 7
    last_friday = now - timedelta(days=days_since_friday)
    last_friday = last_friday.replace(hour=23, minute=59, second=59)

    week_ends = []
    for i in range(WEEKS):
        dt = last_friday - timedelta(weeks=i)
        week_ends.append(int(dt.timestamp()))
    week_ends.reverse()
    return week_ends


def fetch_aave_btc_borrow_rates() -> pd.DataFrame:
    """Fetch 2y of weekly Aave V3 borrow rate snapshots for USDC/USDT on ETH + Base.

    Uses batched GraphQL queries for speed (~30 requests instead of ~300).
    Returns DataFrame: date, chain, symbol, borrow_apy, utilization
    """
    api_key = get_secret("THEGRAPH_API_KEY")
    if not api_key:
        print("  THEGRAPH_API_KEY not set — skipping")
        return pd.DataFrame()

    week_ends = _generate_week_timestamps()
    rows = []

    for chain, reserves in RESERVES.items():
        url = _graph_url(chain)
        if not url:
            continue

        for symbol, reserve_id in reserves.items():
            label = f"{symbol} ({chain})"
            n_batches = (len(week_ends) + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"    Fetching {label}: {len(week_ends)} weeks in {n_batches} batches...")
            fetched = 0

            for batch_start in range(0, len(week_ends), BATCH_SIZE):
                batch_ts = week_ends[batch_start : batch_start + BATCH_SIZE]
                results = _batch_weekly_snapshots(url, reserve_id, batch_ts)

                for ts, item in results.items():
                    rows.append({
                        "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
                        "chain": chain,
                        "symbol": symbol,
                        "borrow_apy": int(item["variableBorrowRate"]) / RAY * 100,
                        "utilization": float(item["utilizationRate"]) * 100,
                    })
                    fetched += 1

                # Small pause between batches to respect rate limits
                time.sleep(0.15)

            print(f"    {label}: {fetched}/{len(week_ends)} weeks collected")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["chain", "symbol", "date"]).reset_index(drop=True)
    return df


def fetch_aave_btc_borrow_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_aave_btc_borrow_rates()
    except Exception as e:
        print(f"  Aave BTC borrow rates fetch failed: {e}")
        return pd.DataFrame()

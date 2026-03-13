"""Fetch historical Aave V3 supply + borrow rates + BTC price.

Rates: The Graph Aave V3 subgraph — one snapshot query per week (fast).
BTC price: DeFi Llama coins chart API.
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

from src.config import get_secret

AAVE_SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
TIMEOUT = 15
RAY = 1e27

# Aave V3 Ethereum reserve IDs (token address + pool address concatenated)
RESERVES = {
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480x2f39d218133afab8f2b819b1066c7e434ad94e9e",
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec70x2f39d218133afab8f2b819b1066c7e434ad94e9e",
}

WEEKS = 104  # 2 years


def _graph_url() -> str | None:
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return None
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{AAVE_SUBGRAPH_ID}"


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
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


def _weekly_snapshot(url: str, reserve_id: str, ts_end: int) -> dict | None:
    """Get the last rate snapshot before ts_end for a reserve."""
    query = """{{
      reserveParamsHistoryItems(
        first: 1,
        orderBy: timestamp,
        orderDirection: desc,
        where: {{ reserve: "{rid}", timestamp_lte: {ts} }}
      ) {{
        timestamp
        liquidityRate
        variableBorrowRate
        utilizationRate
      }}
    }}""".format(rid=reserve_id, ts=ts_end)

    data = _query_graph(url, query)
    if not data:
        return None
    items = data.get("reserveParamsHistoryItems", [])
    return items[0] if items else None


def fetch_aave_rate_history() -> pd.DataFrame:
    """Fetch 2y of weekly Aave V3 rate snapshots via The Graph.

    Strategy: for each Friday over last 2 years, get the most recent
    ReserveParamsHistoryItem before that timestamp. ~208 queries, ~1 min.

    Returns DataFrame: date, symbol, supply_apy, borrow_apy, utilization
    """
    url = _graph_url()
    if not url:
        print("  THEGRAPH_API_KEY not set — skipping Aave rates")
        return pd.DataFrame()

    now = datetime.now(timezone.utc)
    # Generate Friday timestamps for last 2 years
    # Find last Friday
    days_since_friday = (now.weekday() - 4) % 7
    last_friday = now - timedelta(days=days_since_friday)
    last_friday = last_friday.replace(hour=23, minute=59, second=59)

    week_ends = []
    for i in range(WEEKS):
        dt = last_friday - timedelta(weeks=i)
        week_ends.append(int(dt.timestamp()))
    week_ends.reverse()  # oldest first

    rows = []
    for symbol, reserve_id in RESERVES.items():
        print(f"    Fetching {symbol}: {len(week_ends)} weekly snapshots...")
        fetched = 0
        for ts in week_ends:
            item = _weekly_snapshot(url, reserve_id, ts)
            if item:
                rows.append({
                    "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "supply_apy": int(item["liquidityRate"]) / RAY * 100,
                    "borrow_apy": int(item["variableBorrowRate"]) / RAY * 100,
                    "utilization": float(item["utilizationRate"]) * 100,
                })
                fetched += 1
        print(f"    {symbol}: {fetched}/{len(week_ends)} weeks collected")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_btc_price_history(days: int = 730) -> pd.DataFrame:
    """Fetch BTC/USD weekly price from DeFi Llama."""
    start_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    for attempt in range(4):
        try:
            resp = requests.get(
                f"https://coins.llama.fi/chart/coingecko:bitcoin?start={start_ts}&span=200&period=1w",
                timeout=TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(5)
                continue
            resp.raise_for_status()
            prices = resp.json().get("coins", {}).get("coingecko:bitcoin", {}).get("prices", [])
            if not prices:
                return pd.DataFrame()
            df = pd.DataFrame(prices)
            df["date"] = pd.to_datetime(df["timestamp"], unit="s")
            df = df[["date", "price"]].rename(columns={"price": "btc_price"})
            return df
        except Exception:
            if attempt < 3:
                time.sleep(2 ** attempt)
    return pd.DataFrame()


def fetch_aave_rates_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_aave_rate_history()
    except Exception as e:
        print(f"  Aave rates fetch failed: {e}")
        return pd.DataFrame()


def fetch_btc_price_safe(days: int = 730) -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_btc_price_history(days)
    except Exception as e:
        print(f"  BTC price fetch failed: {e}")
        return pd.DataFrame()

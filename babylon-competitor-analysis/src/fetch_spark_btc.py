"""Fetch Spark Lend rates via The Graph (Messari subgraph).

Two datasets:
1. BTC collateral markets (WBTC, cbBTC, LBTC, tBTC) — borrow rates of BTC tokens
2. Stablecoin borrow markets (USDC, USDT, DAI, USDS) — borrow rates borrowers pay
   when they put up BTC as collateral and borrow stablecoins

Uses marketDailySnapshot entity — daily pre-aggregated data, one paginated query per market.
Resampled to weekly (Friday) for dashboard display.
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

from src.config import get_secret

SPARK_SUBGRAPH_ID = "GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si"
TIMEOUT = 15

# Spark Lend Ethereum — BTC market IDs (from subgraph introspection)
SPARK_BTC_MARKETS = {
    "WBTC": "0x4197ba364ae6698015ae5c1468f54087602715b2",
    "cbBTC": "0xb3973d459df38ae57797811f2a1fd061da1bc123",
    "LBTC": "0xa9d4ecebd48c282a70cfd3c469d6c8f178a5738e",
    "tBTC": "0xce6ca9cdce00a2b0c0d1dac93894f4bd2c960567",
}

# Spark Lend Ethereum — Stablecoin market IDs (borrowers borrow these against BTC collateral)
SPARK_STABLE_MARKETS = {
    "USDC": "0x377c3bd93f2a2984e1e7be6a5c22c525ed4a4815",
    "USDT": "0xe7df13b8e3d6740fe17cbe928c7334243d86c92f",
    "DAI": "0x4dedf26112b3ec8ec46e7e31ea5e123490b05b8b",
    "USDS": "0xc02ab1a5eaa8d1b114ef786d9bde108cd4364359",
}

WEEKS_HISTORY = 104  # 2 years


def _graph_url() -> str | None:
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return None
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{SPARK_SUBGRAPH_ID}"


def _fetch_daily_snapshots(url: str, market_id: str, since_ts: int) -> list[dict]:
    """Fetch all daily snapshots for a market since timestamp."""
    all_snaps = []
    last_ts = since_ts

    while True:
        query = """{{
          marketDailySnapshots(
            first: 1000,
            orderBy: timestamp,
            orderDirection: asc,
            where: {{ market: "{mid}", timestamp_gt: {ts} }}
          ) {{
            timestamp
            rates {{ rate side type }}
            totalValueLockedUSD
            totalBorrowBalanceUSD
          }}
        }}""".format(mid=market_id, ts=last_ts)

        for attempt in range(3):
            try:
                resp = requests.post(url, json={"query": query}, timeout=TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data:
                    print(f"    Graph errors: {str(data['errors'])[:200]}")
                    return all_snaps
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            break

        snaps = data.get("data", {}).get("marketDailySnapshots", [])
        if not snaps:
            break

        all_snaps.extend(snaps)
        last_ts = snaps[-1]["timestamp"]

        if len(snaps) < 1000:
            break
        time.sleep(0.3)

    return all_snaps


def _extract_rates(snapshot: dict) -> dict:
    """Extract borrow and supply variable rates from snapshot."""
    rates = {}
    for r in snapshot.get("rates", []):
        key = f"{r['side']}_{r['type']}"
        rates[key] = float(r["rate"])
    return {
        "borrow_rate": rates.get("BORROWER_VARIABLE", 0),
        "supply_rate": rates.get("LENDER_VARIABLE", 0),
    }


def _to_weekly_df(snapshots: list[dict], symbol: str) -> pd.DataFrame:
    """Convert daily snapshots to weekly DataFrame."""
    if not snapshots:
        return pd.DataFrame()

    rows = []
    for s in snapshots:
        rates = _extract_rates(s)
        rows.append({
            "timestamp": int(s["timestamp"]),
            "borrow_rate": rates["borrow_rate"],
            "supply_rate": rates["supply_rate"],
            "tvl_usd": float(s["totalValueLockedUSD"]),
            "borrow_usd": float(s["totalBorrowBalanceUSD"]),
        })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["timestamp"], unit="s")
    df = df.set_index("date").resample("W-Fri").agg({
        "borrow_rate": "mean",
        "supply_rate": "mean",
        "tvl_usd": "last",
        "borrow_usd": "last",
    }).dropna(subset=["borrow_rate"]).reset_index()

    df["symbol"] = symbol
    # Compute utilization
    df["utilization"] = (df["borrow_usd"] / df["tvl_usd"] * 100).clip(0, 100).fillna(0)
    return df


def fetch_spark_btc_rates() -> pd.DataFrame:
    """Fetch Spark Lend BTC borrow rates for all BTC markets.

    Returns DataFrame: date, symbol, borrow_rate, supply_rate, tvl_usd, borrow_usd, utilization
    """
    url = _graph_url()
    if not url:
        print("  THEGRAPH_API_KEY not set — skipping Spark rates")
        return pd.DataFrame()

    since_ts = int((datetime.now(timezone.utc) - timedelta(weeks=WEEKS_HISTORY)).timestamp())
    frames = []

    for symbol, market_id in SPARK_BTC_MARKETS.items():
        print(f"    Fetching Spark {symbol}...")
        snaps = _fetch_daily_snapshots(url, market_id, since_ts)
        print(f"    {symbol}: {len(snaps)} daily snapshots")

        weekly = _to_weekly_df(snaps, symbol)
        if not weekly.empty:
            frames.append(weekly)
            print(f"    {symbol}: {len(weekly)} weekly data points")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def fetch_spark_stable_rates() -> pd.DataFrame:
    """Fetch Spark Lend stablecoin borrow rates (USDC, USDT, DAI, USDS).

    These are the rates borrowers pay when they borrow stablecoins
    against BTC collateral on Spark.

    Returns DataFrame: date, symbol, borrow_rate, supply_rate, tvl_usd, borrow_usd, utilization
    """
    url = _graph_url()
    if not url:
        print("  THEGRAPH_API_KEY not set — skipping Spark stable rates")
        return pd.DataFrame()

    since_ts = int((datetime.now(timezone.utc) - timedelta(weeks=WEEKS_HISTORY)).timestamp())
    frames = []

    for symbol, market_id in SPARK_STABLE_MARKETS.items():
        print(f"    Fetching Spark {symbol}...")
        snaps = _fetch_daily_snapshots(url, market_id, since_ts)
        print(f"    {symbol}: {len(snaps)} daily snapshots")

        weekly = _to_weekly_df(snaps, symbol)
        if not weekly.empty:
            frames.append(weekly)
            print(f"    {symbol}: {len(weekly)} weekly data points")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def fetch_spark_btc_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_spark_btc_rates()
    except Exception as e:
        print(f"  Spark BTC rates fetch failed: {e}")
        return pd.DataFrame()


def fetch_spark_stable_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_spark_stable_rates()
    except Exception as e:
        print(f"  Spark stable rates fetch failed: {e}")
        return pd.DataFrame()

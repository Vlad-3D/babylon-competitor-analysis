"""Fetch Compound V3 (Comet) USDC/USDT borrow rates on Ethereum — weekly, 2 years.

Compound V3 has separate Comet contracts per borrowable asset (USDC, USDT).
Each Comet accepts multiple collateral types including wBTC and cbBTC.
The borrow rate is pooled — same rate regardless of collateral type.

Data source: The Graph — Paperclip Labs Compound V3 subgraph
             (weeklyMarketAccounting entity with accounting.borrowApr).

Subgraph: 5nwMCSHaTqG3Kd2gHznbTXEnZ9QNWsssQfbHhDqQSQFp
"""

import time
import requests
import pandas as pd
from datetime import datetime, timezone

from src.config import get_secret

TIMEOUT = 20

SUBGRAPH_ID = "5nwMCSHaTqG3Kd2gHznbTXEnZ9QNWsssQfbHhDqQSQFp"

# Compound V3 Comet proxy addresses (Ethereum mainnet)
COMET_PROXIES = {
    "USDC": "0xc3d688b66703497daa19211eedff47f25384cdc3",
    "USDT": "0x3afdc9bca9213a35503b077a6072f3d0d5ab0840",
}


def _graph_url() -> str | None:
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return None
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{SUBGRAPH_ID}"


def _query_graph(url: str, query: str) -> dict | None:
    for attempt in range(3):
        try:
            resp = requests.post(url, json={"query": query}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                print(f"    Graph errors: {str(data['errors'])[:200]}")
                return None
            return data.get("data")
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"    Graph request failed: {e}")
    return None


def _fetch_weekly_snapshots(url: str, comet_proxy: str) -> list[dict]:
    """Fetch all weekly snapshots for a market (paginated)."""
    all_items = []
    skip = 0
    page_size = 1000

    while True:
        query = """{
          weeklyMarketAccountings(
            first: %d
            skip: %d
            orderBy: timestamp
            orderDirection: desc
            where: {
              market_: {
                cometProxy: "%s"
              }
            }
          ) {
            timestamp
            week
            accounting {
              borrowApr
              supplyApr
              utilization
              totalBaseBorrowUsd
              totalBaseSupplyUsd
            }
          }
        }""" % (page_size, skip, comet_proxy)

        data = _query_graph(url, query)
        if not data:
            break

        items = data.get("weeklyMarketAccountings", [])
        if not items:
            break

        all_items.extend(items)
        if len(items) < page_size:
            break

        skip += page_size
        time.sleep(0.2)

    return all_items


def fetch_compound_btc_borrow_rates() -> pd.DataFrame:
    """Fetch weekly Compound V3 borrow rate snapshots for USDC/USDT.

    Returns DataFrame: date, symbol, borrow_apy, utilization
    """
    url = _graph_url()
    if not url:
        print("  THEGRAPH_API_KEY not set — skipping Compound")
        return pd.DataFrame()

    rows = []

    for symbol, comet_proxy in COMET_PROXIES.items():
        print(f"    Fetching Compound V3 {symbol} weekly snapshots...")
        items = _fetch_weekly_snapshots(url, comet_proxy)
        print(f"    Compound V3 {symbol}: {len(items)} weekly snapshots fetched")

        for item in items:
            acct = item.get("accounting", {})
            borrow_apr = acct.get("borrowApr")
            if borrow_apr is None:
                continue

            # borrowApr is a decimal (0.05 = 5%), convert to percentage
            borrow_pct = float(borrow_apr) * 100
            utilization = float(acct.get("utilization", 0)) * 100

            ts = int(item["timestamp"])
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)

            rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "symbol": symbol,
                "borrow_apy": borrow_pct,
                "utilization": utilization,
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    return df


def fetch_compound_btc_borrow_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_compound_btc_borrow_rates()
    except Exception as e:
        print(f"  Compound V3 borrow rates fetch failed: {e}")
        return pd.DataFrame()

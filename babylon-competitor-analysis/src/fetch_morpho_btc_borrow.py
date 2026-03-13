"""Fetch Morpho Blue USDC/USDT borrow rates for BTC collateral — weekly, 2 years.

Morpho Blue has isolated markets (each collateral/loan pair = separate pool with its own rate).
We track the largest USDC and USDT markets with BTC collateral on Ethereum:
  - USDC / WBTC  (data from Jan 2024, ~$254M TVL)
  - USDT / WBTC  (data from Feb 2024, ~$164M TVL)
  - USDC / cbBTC (data from Sep 2024, ~$432M TVL)

For Base, the subgraph has broken USD price feeds, so we use Ethereum only.
Base Morpho data can be added later via Morpho Blue API if historical snapshots appear.

Data source: The Graph — Morpho Blue subgraph, MarketDailySnapshot (sampled every 7 days).
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

from src.config import get_secret

TIMEOUT = 20
WEEKS = 104  # 2 years

MORPHO_SUBGRAPH_ID = "8Lz789DP5VKLXumTMTgygjU2xtuzx8AhbaacgN5PYCAs"

# Morpho Blue Ethereum — largest BTC collateral markets
MORPHO_MARKETS = {
    "USDC": [
        {
            "id": "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49",
            "collateral": "WBTC",
            "earliest_day": 19741,  # Jan 2024
        },
        {
            "id": "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64",
            "collateral": "cbBTC",
            "earliest_day": 19978,  # Sep 2024
        },
    ],
    "USDT": [
        {
            "id": "0xa921ef34e2fc7a27ccc50ae7e4b154e16c9799d3387076c421423ef52ac4df99",
            "collateral": "WBTC",
            "earliest_day": 19758,  # Feb 2024
        },
    ],
}

# Max items The Graph returns per query
BATCH_SIZE = 50


def _graph_url() -> str | None:
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return None
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{MORPHO_SUBGRAPH_ID}"


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


def _generate_weekly_days() -> list[int]:
    """Generate day numbers (epoch days) for every Friday over the last 2 years."""
    now = datetime.now(timezone.utc)
    days_since_friday = (now.weekday() - 4) % 7
    last_friday = now - timedelta(days=days_since_friday)
    last_friday = last_friday.replace(hour=23, minute=59, second=59)

    day_numbers = []
    for i in range(WEEKS):
        dt = last_friday - timedelta(weeks=i)
        epoch_day = int(dt.timestamp()) // 86400
        day_numbers.append(epoch_day)
    day_numbers.reverse()
    return day_numbers


def _day_to_date(day_num: int) -> str:
    """Convert epoch day number to YYYY-MM-DD string."""
    return datetime.fromtimestamp(day_num * 86400, tz=timezone.utc).strftime("%Y-%m-%d")


def _fetch_market_snapshots(
    url: str, market_id: str, day_numbers: list[int]
) -> list[dict]:
    """Fetch daily snapshots for specific days using days_in filter."""
    all_snaps = []

    for batch_start in range(0, len(day_numbers), BATCH_SIZE):
        batch = day_numbers[batch_start : batch_start + BATCH_SIZE]
        days_list = ", ".join(str(d) for d in batch)

        query = f"""{{
          marketDailySnapshots(
            first: {len(batch)},
            where: {{
              market: "{market_id}",
              days_in: [{days_list}]
            }}
          ) {{
            days
            timestamp
            rates {{ rate side type }}
            totalBorrowBalanceUSD
            totalDepositBalanceUSD
          }}
        }}"""

        data = _query_graph(url, query)
        if data and "marketDailySnapshots" in data:
            all_snaps.extend(data["marketDailySnapshots"])

        time.sleep(0.15)

    return all_snaps


def fetch_morpho_btc_borrow_rates() -> pd.DataFrame:
    """Fetch weekly Morpho Blue borrow rates for BTC collateral markets.

    For each stablecoin (USDC, USDT), if multiple BTC-collateral markets exist,
    we compute a borrow-weighted average rate for each week.

    Returns DataFrame: date, symbol, borrow_apy, protocol
    """
    url = _graph_url()
    if not url:
        print("  THEGRAPH_API_KEY not set — skipping Morpho")
        return pd.DataFrame()

    weekly_days = _generate_weekly_days()
    rows = []

    for symbol, markets in MORPHO_MARKETS.items():
        # Collect snapshots from all markets for this stablecoin
        market_data: dict[int, list[dict]] = {}  # day -> list of {rate, borrow_usd}

        for mkt in markets:
            # Filter days to those after this market existed
            valid_days = [d for d in weekly_days if d >= mkt["earliest_day"]]
            label = f"{symbol}/{mkt['collateral']}"
            n_batches = (len(valid_days) + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"    Fetching Morpho {label}: {len(valid_days)} weeks in {n_batches} batches...")

            snaps = _fetch_market_snapshots(url, mkt["id"], valid_days)
            fetched = 0
            for snap in snaps:
                day = snap["days"]
                borrow_rate = None
                for r in snap.get("rates", []):
                    if r["side"] == "BORROWER" and r["type"] == "VARIABLE":
                        borrow_rate = float(r["rate"])
                        break
                if borrow_rate is not None:
                    borrow_usd = float(snap.get("totalBorrowBalanceUSD", 0) or 0)
                    deposit_usd = float(snap.get("totalDepositBalanceUSD", 0) or 0)
                    if day not in market_data:
                        market_data[day] = []
                    market_data[day].append({
                        "rate": borrow_rate,
                        "borrow_usd": borrow_usd,
                        "deposit_usd": deposit_usd,
                    })
                    fetched += 1

            print(f"    Morpho {label}: {fetched} snapshots collected")

        # Compute borrow-weighted average rate per week
        for day, entries in sorted(market_data.items()):
            total_borrow = sum(e["borrow_usd"] for e in entries)
            total_deposit = sum(e["deposit_usd"] for e in entries)
            if total_borrow > 0:
                weighted_rate = sum(e["rate"] * e["borrow_usd"] for e in entries) / total_borrow
            else:
                # Equal weight if no borrow data
                weighted_rate = sum(e["rate"] for e in entries) / len(entries)

            utilization = (total_borrow / total_deposit * 100) if total_deposit > 0 else 0.0

            rows.append({
                "date": _day_to_date(day),
                "symbol": symbol,
                "borrow_apy": weighted_rate * 100,  # Convert to percentage
                "utilization": utilization,
                "protocol": "morpho",
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    return df


def fetch_morpho_btc_borrow_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_morpho_btc_borrow_rates()
    except Exception as e:
        print(f"  Morpho BTC borrow rates fetch failed: {e}")
        return pd.DataFrame()

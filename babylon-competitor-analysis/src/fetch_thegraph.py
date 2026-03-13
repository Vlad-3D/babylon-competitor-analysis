"""Fetch on-chain data from The Graph (Aave V3 + Uniswap V3). Requires THEGRAPH_API_KEY."""

import time
import requests
import pandas as pd
from src.config import get_secret

AAVE_SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
TIMEOUT = 10
MAX_RETRIES = 3

BTC_SYMBOLS = ["WBTC", "cbBTC", "tBTC", "LBTC"]


def _get_btc_price() -> float:
    """Get BTC/USD price from DeFi Llama."""
    try:
        resp = requests.get(
            "https://coins.llama.fi/prices/current/coingecko:bitcoin",
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()["coins"]["coingecko:bitcoin"]["price"]
    except Exception:
        return 85000.0  # fallback


def _query_graph(subgraph_id: str, query: str, api_key: str) -> dict | None:
    url = f"https://gateway.thegraph.com/api/{api_key}/subgraphs/id/{subgraph_id}"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, json={"query": query}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                print(f"Graph query errors: {data['errors']}")
                return None
            return data.get("data")
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None


def fetch_aave_reserves(api_key: str) -> pd.DataFrame:
    """Fetch Aave V3 reserve data for BTC assets."""
    symbols_str = ", ".join(f'"{s}"' for s in BTC_SYMBOLS)
    query = f"""{{
      reserves(where: {{ symbol_in: [{symbols_str}] }}) {{
        symbol
        name
        decimals
        totalATokenSupply
        totalCurrentVariableDebt
        availableLiquidity
        baseLTVasCollateral
        reserveLiquidationThreshold
        utilizationRate
      }}
    }}"""

    data = _query_graph(AAVE_SUBGRAPH_ID, query, api_key)
    if not data or "reserves" not in data:
        return pd.DataFrame()

    btc_price = _get_btc_price()

    rows = []
    for r in data["reserves"]:
        supply_raw = float(r.get("totalATokenSupply", 0) or 0)
        debt_raw = float(r.get("totalCurrentVariableDebt", 0) or 0)

        decimals = int(r.get("decimals", 8))
        supply = supply_raw / (10 ** decimals)
        debt = debt_raw / (10 ** decimals)

        supply_usd = supply * btc_price
        debt_usd = debt * btc_price
        utilization = float(r.get("utilizationRate", 0) or 0)
        ltv = float(r.get("baseLTVasCollateral", 0) or 0) / 100
        liq_threshold = float(r.get("reserveLiquidationThreshold", 0) or 0) / 100

        rows.append({
            "aave_symbol": r["symbol"],
            "aave_name": r["name"],
            "aave_supply_usd": round(supply_usd, 2),
            "aave_borrow_usd": round(debt_usd, 2),
            "aave_utilization": round(utilization * 100, 2),
            "aave_ltv_onchain": round(ltv, 2),
            "aave_liq_threshold": round(liq_threshold, 2),
            "aave_price_usd": round(btc_price, 2),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_thegraph() -> pd.DataFrame:
    """Fetch all Graph data. Returns empty DataFrame if no API key."""
    api_key = get_secret("THEGRAPH_API_KEY")
    if not api_key:
        return pd.DataFrame()

    aave_df = fetch_aave_reserves(api_key)
    # Uniswap can be added later — Aave is higher priority
    return aave_df


def fetch_thegraph_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_thegraph()
    except Exception as e:
        print(f"The Graph fetch failed: {e}")
        return pd.DataFrame()

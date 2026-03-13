"""Fetch Maple Finance (Syrup) lending yields — weekly, from DefiLlama yields API.

Maple is an institutional lending platform. Borrowers (trading firms, miners)
borrow stablecoins (USDC, USDT) against BTC collateral via KYC-gated,
off-chain-negotiated loans with 120-170% overcollateralisation.

On-chain, lenders deposit into syrupUSDC / syrupUSDT ERC-4626 vaults and earn
yield from those institutional BTC-collateral loans.

We track the **lending yield** (what vault depositors earn) as a proxy for borrow
rates. The actual institutional borrow rate = lending yield + Maple protocol fee.

Data source: DefiLlama yields chart API (daily, resampled to weekly Friday).
"""

import requests
import pandas as pd
from datetime import datetime, timezone

TIMEOUT = 20

# DefiLlama pool IDs for Maple / Syrup vaults (Ethereum)
MAPLE_POOLS = {
    "USDC": "43641cf5-a92e-416b-bce9-27113d3c0db6",  # syrupUSDC
    "USDT": "8edfdf02-cdbb-43f7-bca6-954e5fe56813",  # syrupUSDT
}


def _fetch_pool_chart(pool_id: str) -> list[dict]:
    """Fetch historical APY data for a DefiLlama pool."""
    url = f"https://yields.llama.fi/chart/{pool_id}"
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        print(f"    DefiLlama yields fetch failed: {e}")
        return []


def fetch_maple_btc_borrow_rates() -> pd.DataFrame:
    """Fetch Maple/Syrup lending yields as a proxy for BTC-collateral borrow rates.

    Returns DataFrame: date, symbol, borrow_apy, tvl_usd, protocol
    """
    rows = []

    for symbol, pool_id in MAPLE_POOLS.items():
        print(f"    Fetching Maple syrup{symbol} from DefiLlama...")
        data = _fetch_pool_chart(pool_id)

        if not data:
            print(f"    syrup{symbol}: no data returned")
            continue

        for point in data:
            apy_base = point.get("apyBase")
            if apy_base is None:
                continue
            rows.append({
                "date": point["timestamp"][:10],  # YYYY-MM-DD
                "symbol": symbol,
                "borrow_apy": apy_base,
                "tvl_usd": point.get("tvlUsd", 0),
                "protocol": "maple",
            })

        print(f"    syrup{symbol}: {len([r for r in rows if r['symbol'] == symbol])} data points")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    # Resample to weekly (Friday) to match other protocols
    frames = []
    for symbol in df["symbol"].unique():
        sub = df[df["symbol"] == symbol].set_index("date").sort_index()
        weekly = sub.resample("W-FRI").agg({
            "borrow_apy": "mean",
            "tvl_usd": "last",
            "protocol": "first",
        }).dropna(subset=["borrow_apy"]).reset_index()
        weekly["symbol"] = symbol
        frames.append(weekly)

    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    return df


def fetch_maple_btc_borrow_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_maple_btc_borrow_rates()
    except Exception as e:
        print(f"  Maple lending yields fetch failed: {e}")
        return pd.DataFrame()

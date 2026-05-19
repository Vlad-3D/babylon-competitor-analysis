"""Append today's snapshot to historical rate CSVs.

NON-DESTRUCTIVE — appends rows at the byte level. Historical lines stay
byte-for-byte identical (no pandas re-serialization). If today's date already
exists for a symbol, today's rows are replaced; older rows are untouched.

Run:  uv run python append_today_snapshot.py
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "api-keys.env")

if "GRAPH_API_KEY" in os.environ and "THEGRAPH_API_KEY" not in os.environ:
    os.environ["THEGRAPH_API_KEY"] = os.environ["GRAPH_API_KEY"]

from src.config import get_secret

DATA = Path(__file__).parent / "data"
TIMEOUT = 15
RAY = 1e27
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

AAVE_SUBGRAPH = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
SPARK_SUBGRAPH = "GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si"
MORPHO_SUBGRAPH = "8Lz789DP5VKLXumTMTgygjU2xtuzx8AhbaacgN5PYCAs"
COMPOUND_SUBGRAPH = "5nwMCSHaTqG3Kd2gHznbTXEnZ9QNWsssQfbHhDqQSQFp"

AAVE_RESERVES = {
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480x2f39d218133afab8f2b819b1066c7e434ad94e9e",
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec70x2f39d218133afab8f2b819b1066c7e434ad94e9e",
}
SPARK_STABLE_MARKETS = {
    "USDC": "0x377c3bd93f2a2984e1e7be6a5c22c525ed4a4815",
    "USDT": "0xe7df13b8e3d6740fe17cbe928c7334243d86c92f",
    "DAI": "0x4dedf26112b3ec8ec46e7e31ea5e123490b05b8b",
    "USDS": "0xc02ab1a5eaa8d1b114ef786d9bde108cd4364359",
}
MORPHO_MARKETS = {
    "USDC": [
        "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49",
        "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64",
    ],
    "USDT": [
        "0xa921ef34e2fc7a27ccc50ae7e4b154e16c9799d3387076c421423ef52ac4df99",
    ],
}
COMPOUND_COMETS = {
    "USDC": "0xc3d688b66703497daa19211eedff47f25384cdc3",
    "USDT": "0x3afdc9bca9213a35503b077a6072f3d0d5ab0840",
}


def _gql(subgraph_id: str, query: str) -> dict:
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        raise RuntimeError("THEGRAPH_API_KEY not set")
    url = f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{subgraph_id}"
    r = requests.post(url, json={"query": query}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("data") or {}


def append_lines(csv_path: Path, new_lines: list[str], symbol_filter_fn) -> int:
    """Append raw CSV lines. If a row for TODAY already exists for one of our
    symbols, it's removed first (so re-running same day overwrites today only).
    Older rows are kept byte-for-byte.

    symbol_filter_fn(line: str) -> str | None : returns the symbol if this line
        is one of "ours for today", else None.
    """
    if not new_lines:
        return 0

    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            existing = f.read()
        lines = existing.splitlines(keepends=True)
    else:
        lines = []

    # Drop existing rows where date matches TODAY AND symbol is in our set
    today_symbols = {symbol_filter_fn(line) for line in new_lines if symbol_filter_fn(line)}
    today_symbols = {s for s in today_symbols if s}

    kept = []
    for line in lines:
        if line.startswith(TODAY + ","):
            sym = symbol_filter_fn(line)
            if sym and sym in today_symbols:
                continue  # drop — will be replaced
        kept.append(line)

    # Ensure trailing newline before appending
    if kept and not kept[-1].endswith("\n"):
        kept[-1] = kept[-1] + "\n"

    # Append new lines (each must already end with \n)
    out = "".join(kept) + "".join(new_lines)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(out)

    print(f"  [ok]   {csv_path.name}: +{len(new_lines)} row(s) for {TODAY}")
    return len(new_lines)


def _sym_aave(line):
    parts = line.split(",")
    return parts[1] if len(parts) >= 2 else None


def _sym_morpho(line):
    parts = line.split(",")
    return parts[1] if len(parts) >= 2 else None


def _sym_spark(line):
    # spark_stable.csv columns: date,borrow_rate,supply_rate,tvl_usd,borrow_usd,symbol,utilization
    parts = line.split(",")
    return parts[5] if len(parts) >= 6 else None


def _sym_compound(line):
    parts = line.split(",")
    return parts[1] if len(parts) >= 2 else None


# ---------------- Aave V3 ----------------

def snapshot_aave():
    rows = []
    for sym, rid in AAVE_RESERVES.items():
        q = f'{{ reserve(id: "{rid}") {{ liquidityRate variableBorrowRate utilizationRate }} }}'
        r = (_gql(AAVE_SUBGRAPH, q).get("reserve") or {})
        if not r:
            print(f"  [warn] Aave {sym}: empty")
            continue
        supply = int(r["liquidityRate"]) / RAY * 100
        borrow = int(r["variableBorrowRate"]) / RAY * 100
        util = float(r["utilizationRate"]) * 100
        # Match column order from existing CSV: date,symbol,supply_apy,borrow_apy,utilization
        rows.append(f"{TODAY},{sym},{supply},{borrow},{util}\n")
    append_lines(DATA / "aave_rates.csv", rows, _sym_aave)


# ---------------- Spark Lend ----------------

def snapshot_spark():
    rows = []
    for sym, mid in SPARK_STABLE_MARKETS.items():
        q = f'''{{
          market(id: "{mid}") {{
            totalValueLockedUSD totalBorrowBalanceUSD
            rates {{ rate side type }}
          }}
        }}'''
        m = (_gql(SPARK_SUBGRAPH, q).get("market") or {})
        if not m:
            continue
        tvl = float(m.get("totalValueLockedUSD") or 0)
        borrow = float(m.get("totalBorrowBalanceUSD") or 0)
        br = sr = 0.0
        for rate in m.get("rates", []) or []:
            if rate.get("side") == "BORROWER" and rate.get("type") == "VARIABLE":
                br = float(rate.get("rate") or 0)
            elif rate.get("side") == "LENDER" and rate.get("type") == "VARIABLE":
                sr = float(rate.get("rate") or 0)
        util = (borrow / tvl * 100) if tvl > 0 else 0.0
        # Column order: date,borrow_rate,supply_rate,tvl_usd,borrow_usd,symbol,utilization
        rows.append(f"{TODAY},{br},{sr},{tvl},{borrow},{sym},{util}\n")
    append_lines(DATA / "spark_stable.csv", rows, _sym_spark)


# ---------------- Morpho Blue ----------------

def snapshot_morpho():
    rows = []
    for sym, market_ids in MORPHO_MARKETS.items():
        weighted_sum = 0.0
        total_borrow_for_w = 0.0
        total_borrow = 0.0
        total_deposit = 0.0
        for mid in market_ids:
            q = f'''{{
              market(id: "{mid}") {{
                totalBorrowBalanceUSD totalDepositBalanceUSD
                rates {{ rate side type }}
              }}
            }}'''
            m = (_gql(MORPHO_SUBGRAPH, q).get("market") or {})
            if not m:
                continue
            rate = 0.0
            for r in m.get("rates", []) or []:
                if r.get("side") == "BORROWER" and r.get("type") == "VARIABLE":
                    rate = float(r.get("rate") or 0)
                    break
            borrow_usd = float(m.get("totalBorrowBalanceUSD") or 0)
            deposit_usd = float(m.get("totalDepositBalanceUSD") or 0)
            w = max(borrow_usd, 1.0)
            weighted_sum += rate * w
            total_borrow_for_w += w
            total_borrow += borrow_usd
            total_deposit += deposit_usd
        if total_borrow_for_w > 0:
            avg_pct = weighted_sum / total_borrow_for_w * 100
            util = (total_borrow / total_deposit * 100) if total_deposit > 0 else 0.0
            # Existing column order: date,symbol,borrow_apy,utilization,protocol
            rows.append(f"{TODAY},{sym},{avg_pct},{util},morpho\n")
    append_lines(DATA / "morpho_btc_borrow.csv", rows, _sym_morpho)


# ---------------- Compound V3 ----------------

def snapshot_compound():
    rows = []
    for sym, comet in COMPOUND_COMETS.items():
        q = f'''{{
          markets(where: {{ cometProxy: "{comet}" }}) {{
            accounting {{ borrowApr utilization }}
          }}
        }}'''
        items = _gql(COMPOUND_SUBGRAPH, q).get("markets") or []
        if not items:
            continue
        a = items[0].get("accounting") or {}
        borrow = float(a.get("borrowApr") or 0) * 100
        util = float(a.get("utilization") or 0) * 100
        # Existing column order: date,symbol,borrow_apy,utilization
        rows.append(f"{TODAY},{sym},{borrow},{util}\n")
    append_lines(DATA / "compound_btc_borrow.csv", rows, _sym_compound)


def main():
    print(f"Appending today ({TODAY}) — historical rows preserved byte-for-byte.\n")
    print("Aave V3 USDC/USDT...")
    snapshot_aave()
    print("Spark Lend USDC/USDT/DAI/USDS...")
    snapshot_spark()
    print("Morpho Blue (borrow-weighted across BTC-collateral markets)...")
    snapshot_morpho()
    print("Compound V3 USDC/USDT...")
    snapshot_compound()
    print("\nDone.")


if __name__ == "__main__":
    main()

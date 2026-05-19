"""Fetch REAL Reserve Factor history for USDC/USDT across lending protocols.

Data sources (only real on-chain data — no projections / extrapolation):

- Aave V3 (Ethereum):    Etherscan logs for `ReserveFactorChanged(address,uint256,uint256)`
                         emitted by PoolConfigurator. Each event records exact block,
                         timestamp, old and new RF (in basis points).
- Spark Lend (Ethereum): same event signature on Spark's PoolConfigurator (Aave fork).
- Morpho Blue (Ethereum):`SetFee(bytes32,uint256)` events. Plus market creation
                         (`CreateMarket`) — initial fee is 0 unless set later.
- Compound V3:           NO explicit reserveFactor parameter. We compute weekly
                         implicit RF = 1 − supplyApr / (borrowApr × utilization)
                         from real subgraph snapshots (already collected).

The output `data/reserve_factor.csv` contains the actual event timeline at monthly
resolution: we ffill the last known RF value between events to produce a monthly
series (because RF is a step function — it stays at its last value until the next
governance change).

Output columns: date, protocol, symbol, reserve_factor (%)
"""

import time
from datetime import datetime, timezone
import requests
import pandas as pd

from src.config import get_secret

ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
CHAIN_ID = "1"  # Ethereum mainnet
TIMEOUT = 30

# topic0 = keccak256(event signature)
TOPIC_RF_CHANGED = "0xb46e2b82b0c2cf3d7d9dece53635e165c53e0eaa7a44f904d61a2b7174826aef"
TOPIC_SET_FEE = "0x139d6f58e9a127229667c8e3b36e88890a66cfc8ab1024ddc513e189e125b75b"

# Pool configurators
AAVE_V3_POOL_CONFIG = "0x64b761D848206f447Fe2dd461b0c635Ec39EbB27"
SPARK_POOL_CONFIG = "0x542DBa469bdE58FAeE189ffB60C6b49CE60E5738"

# Morpho Blue singleton
MORPHO_BLUE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"

# Asset addresses (USDC, USDT)
ASSETS = {
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
}

# Morpho Blue BTC-collateral markets (USDC/USDT loan asset)
MORPHO_MARKETS = {
    "USDC": [
        {"id": "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49", "label": "USDC/WBTC"},
        {"id": "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64", "label": "USDC/cbBTC"},
    ],
    "USDT": [
        {"id": "0xa921ef34e2fc7a27ccc50ae7e4b154e16c9799d3387076c421423ef52ac4df99", "label": "USDT/WBTC"},
    ],
}

# Compound V3 subgraph (same as fetch_compound_btc_borrow.py)
COMPOUND_SUBGRAPH_ID = "5nwMCSHaTqG3Kd2gHznbTXEnZ9QNWsssQfbHhDqQSQFp"
COMPOUND_COMETS = {
    "USDC": "0xc3d688b66703497daa19211eedff47f25384cdc3",
    "USDT": "0x3afdc9bca9213a35503b077a6072f3d0d5ab0840",
}


# -------------------- Etherscan helpers --------------------

def _etherscan_logs(address: str, topic0: str, topic1: str | None = None) -> list[dict]:
    """Return ALL logs for a contract+topic combination (paginated)."""
    key = get_secret("ETHERSCAN_API_KEY")
    if not key:
        print("    ETHERSCAN_API_KEY not set")
        return []

    from_block = 0
    all_logs = []
    while True:
        params = {
            "chainid": CHAIN_ID,
            "module": "logs", "action": "getLogs",
            "address": address,
            "topic0": topic0,
            "fromBlock": str(from_block), "toBlock": "latest",
            "apikey": key,
        }
        if topic1:
            params["topic1"] = topic1
            params["topic0_1_opr"] = "and"
        for attempt in range(3):
            try:
                r = requests.get(ETHERSCAN_BASE, params=params, timeout=TIMEOUT)
                r.raise_for_status()
                data = r.json()
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    return all_logs

        result = data.get("result", [])
        if data.get("status") == "0" and isinstance(result, str):
            # Either "No records found" (ok) or actual error
            if "No records" not in result:
                print(f"    Etherscan error: {result[:200]}")
            break
        if not isinstance(result, list) or not result:
            break

        all_logs.extend(result)
        if len(result) < 1000:
            break
        # paginate by lastBlock + 1
        try:
            from_block = int(result[-1]["blockNumber"], 16) + 1
        except Exception:
            break
        time.sleep(0.25)
    return all_logs


def _parse_uint256_pair(data_hex: str) -> tuple[int, int]:
    """Parse 'data' field with two consecutive uint256 values."""
    h = data_hex[2:] if data_hex.startswith("0x") else data_hex
    return int(h[0:64], 16), int(h[64:128], 16)


def _parse_uint256(data_hex: str) -> int:
    h = data_hex[2:] if data_hex.startswith("0x") else data_hex
    return int(h[:64], 16)


# -------------------- Aave V3 / Spark Lend --------------------

def _fetch_aave_like(protocol: str, pool_config: str) -> list[dict]:
    """Fetch ReserveFactorChanged events for USDC + USDT from given PoolConfigurator."""
    out = []
    for symbol, asset in ASSETS.items():
        padded = "0x" + "0" * 24 + asset[2:]
        logs = _etherscan_logs(pool_config, TOPIC_RF_CHANGED, topic1=padded)
        print(f"    {protocol} {symbol}: {len(logs)} events")
        for ev in logs:
            ts = int(ev["timeStamp"], 16)
            _, new_rf = _parse_uint256_pair(ev["data"])
            out.append({
                "timestamp": ts,
                "protocol": protocol,
                "symbol": symbol,
                "reserve_factor": new_rf / 10000 * 100,  # bps -> %
            })
    return out


# -------------------- Morpho Blue --------------------

def _fetch_morpho_market_events(market_id: str) -> list[tuple[int, float]]:
    """Get (timestamp, fee_pct) timeline for a single Morpho market.

    Morpho Blue markets start with fee=0 at creation. We add a synthetic
    'creation' point at the block of the first known event (or 0 if no
    SetFee events were emitted, which means fee has always been 0).
    """
    logs = _etherscan_logs(MORPHO_BLUE, TOPIC_SET_FEE, topic1=market_id)
    points = []
    for ev in logs:
        ts = int(ev["timeStamp"], 16)
        fee_raw = _parse_uint256(ev["data"])
        # Morpho fee is in 1e18 scale (0.05e18 = 5%)
        fee_pct = fee_raw / 1e18 * 100
        points.append((ts, fee_pct))
    return points


def _fetch_morpho() -> list[dict]:
    out = []
    for symbol, markets in MORPHO_MARKETS.items():
        for mkt in markets:
            points = _fetch_morpho_market_events(mkt["id"])
            print(f"    Morpho {mkt['label']}: {len(points)} SetFee events")
            # If no SetFee events, fee has been 0 since market creation.
            # We need a starting timestamp — use Morpho Blue deployment (Jan 2024)
            # for the "since creation" anchor. Better: query CreateMarket event.
            if not points:
                # Find market creation block: query Morpho Blue contract for
                # CreateMarket event with this market id as indexed param.
                create_logs = _etherscan_logs(
                    MORPHO_BLUE,
                    "0xac4b2400f169220b0c0afdde7a0b32e775ba727ea1cb30b35f935cdaab8683ac",
                    topic1=mkt["id"],
                )
                if create_logs:
                    ts = int(create_logs[0]["timeStamp"], 16)
                    points = [(ts, 0.0)]
                else:
                    continue
            for ts, fee_pct in points:
                out.append({
                    "timestamp": ts,
                    "protocol": "Morpho Blue",
                    "symbol": symbol,
                    "market_label": mkt["label"],
                    "reserve_factor": fee_pct,
                })
    return out


# -------------------- Compound V3 implicit RF --------------------

def _fetch_compound_implicit() -> list[dict]:
    """Compute implicit weekly RF from Compound V3 subgraph snapshots.

    Implicit RF = 1 − supplyApr / (borrowApr × utilization).
    This is the fraction of borrower interest the protocol keeps as reserves
    (since Compound V3 has no explicit reserveFactor parameter).
    """
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        print("    THEGRAPH_API_KEY not set — skipping Compound RF")
        return []
    url = f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{COMPOUND_SUBGRAPH_ID}"

    out = []
    for symbol, comet in COMPOUND_COMETS.items():
        all_items = []
        skip = 0
        while True:
            q = f"""{{
              weeklyMarketAccountings(
                first: 1000, skip: {skip},
                orderBy: timestamp, orderDirection: asc,
                where: {{ market_: {{ cometProxy: "{comet}" }} }}
              ) {{
                timestamp
                accounting {{ borrowApr supplyApr utilization }}
              }}
            }}"""
            try:
                r = requests.post(url, json={"query": q}, timeout=30)
                r.raise_for_status()
                items = r.json().get("data", {}).get("weeklyMarketAccountings", []) or []
            except Exception:
                break
            if not items:
                break
            all_items.extend(items)
            if len(items) < 1000:
                break
            skip += 1000
            time.sleep(0.2)

        print(f"    Compound V3 {symbol}: {len(all_items)} weekly snapshots")
        for it in all_items:
            a = it.get("accounting") or {}
            try:
                br = float(a.get("borrowApr") or 0)
                sr = float(a.get("supplyApr") or 0)
                util = float(a.get("utilization") or 0)
                if br <= 0 or util <= 0:
                    continue
                rf = (1 - sr / (br * util)) * 100
                if rf < 0 or rf > 50:
                    continue  # outlier / bad snapshot
                out.append({
                    "timestamp": int(it["timestamp"]),
                    "protocol": "Compound V3",
                    "symbol": symbol,
                    "reserve_factor": rf,
                })
            except Exception:
                continue
    return out


# -------------------- Aggregator --------------------

def _to_monthly(events: list[dict]) -> pd.DataFrame:
    """Resample event-based RF history to monthly with step (forward-fill).

    Each (protocol, symbol) is treated independently. We:
      1. Build a per-day step series from sparse events using ffill.
      2. Resample to month-start, taking the last value of each month.
    For (protocol, symbol) combos with multiple market_labels (Morpho),
    take borrow-weighted average per timestamp (here equal-weight as fallback).
    """
    if not events:
        return pd.DataFrame()
    df = pd.DataFrame(events)
    df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_localize(None)

    # Normalize all event timestamps to day-level so reindex/resample align correctly
    df["date"] = df["date"].dt.normalize()

    out_frames = []
    for (proto, sym), grp in df.groupby(["protocol", "symbol"]):
        # If multiple markets per symbol (Morpho), per-day equal-weight avg
        if "market_label" in grp.columns and grp["market_label"].notna().any():
            daily = (
                grp.groupby("date")["reserve_factor"]
                .mean()
                .reset_index()
            )
            series = daily.set_index("date")["reserve_factor"].sort_index()
        else:
            # Multiple events on the same day: keep the last one
            series = (
                grp.sort_values("timestamp")
                .drop_duplicates("date", keep="last")
                .set_index("date")["reserve_factor"]
                .sort_index()
            )

        # Build daily step series with ffill from earliest event to today
        start = series.index.min()
        end = pd.Timestamp.now().normalize()
        if end < start:
            end = start
        daily_idx = pd.date_range(start, end, freq="D")
        daily_series = series.reindex(daily_idx, method="ffill")

        # Resample to month-start, taking last value
        monthly = daily_series.resample("MS").last().dropna()
        if monthly.empty:
            # Single observation, current month only — emit just that point
            monthly = pd.Series([series.iloc[-1]], index=[series.index[-1].to_period("M").to_timestamp()])

        out = monthly.reset_index()
        out.columns = ["date", "reserve_factor"]
        out["protocol"] = proto
        out["symbol"] = sym
        out_frames.append(out[["date", "protocol", "symbol", "reserve_factor"]])

    if not out_frames:
        return pd.DataFrame()
    return pd.concat(out_frames, ignore_index=True).sort_values(["protocol", "symbol", "date"])


SPARK_SUBGRAPH_ID = "GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si"
SPARK_MARKETS = {
    "USDC": "0x377c3bd93f2a2984e1e7be6a5c22c525ed4a4815",
    "USDT": "0xe7df13b8e3d6740fe17cbe928c7334243d86c92f",
}


def _fetch_spark_current() -> list[dict]:
    """Spark Lend RF history isn't directly tracked on-chain in a queryable way
    (parameter changes are routed via Maker spells, not via standard
    PoolConfigurator events). Return a single recent data point per asset using
    the subgraph's current value — keeps the chart honest (no projection).
    """
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return []
    url = f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{SPARK_SUBGRAPH_ID}"
    now_ts = int(datetime.now(timezone.utc).timestamp())
    out = []
    for symbol, mid in SPARK_MARKETS.items():
        q = f'{{ market(id: "{mid}") {{ reserveFactor }} }}'
        try:
            r = requests.post(url, json={"query": q}, timeout=15).json()
            rf = r.get("data", {}).get("market", {}).get("reserveFactor")
            if rf is None:
                continue
            out.append({
                "timestamp": now_ts,
                "protocol": "Spark Lend",
                "symbol": symbol,
                "reserve_factor": float(rf) * 100,
            })
        except Exception:
            continue
    print(f"    Spark Lend: {len(out)} current values (history not on-chain via standard events)")
    return out


def fetch_reserve_factor() -> pd.DataFrame:
    print("  [Aave V3] ReserveFactorChanged events via Etherscan...")
    aave = _fetch_aave_like("Aave V3", AAVE_V3_POOL_CONFIG)

    print("  [Spark Lend] current RF via subgraph (no on-chain history available)...")
    spark = _fetch_spark_current()

    print("  [Morpho Blue] SetFee + CreateMarket events via Etherscan...")
    morpho = _fetch_morpho()

    # Compound V3: no explicit reserveFactor parameter — protocol earns from the
    # spread between two independent rate curves. We surface the implicit RF
    # (1 − supplyApr / (borrowApr × utilization)) so users can compare
    # protocol economics across all four lenders on the same axis.
    print("  [Compound V3] implicit RF from weekly spread snapshots...")
    compound = _fetch_compound_implicit()

    df = _to_monthly(aave + spark + morpho + compound)
    return df


def fetch_reserve_factor_safe() -> pd.DataFrame:
    try:
        return fetch_reserve_factor()
    except Exception as e:
        print(f"  Reserve factor fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

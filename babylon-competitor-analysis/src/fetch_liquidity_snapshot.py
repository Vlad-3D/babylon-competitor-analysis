"""Fetch CURRENT pool-level liquidity & BTC collateral sizes across lending protocols.

Two outputs:
  1) data/liquidity_stablecoin.csv — per (protocol, market, symbol):
       symbol = USDC/USDT, market = pool-level or per-Morpho-market
       columns: protocol, market_label, symbol, supply_usd, borrow_usd,
                available_usd, utilization (%)

  2) data/liquidity_btc_collateral.csv — per (protocol, btc_symbol):
       columns: protocol, btc_symbol, supplied_usd, supplied_btc

Pool-level approach for Aave/Spark/Compound (their USDC/USDT pools are shared
across all collateral types) + per-market Morpho data + BTC collateral
sizes for cross-protocol context.
"""

import time
import requests
import pandas as pd
from pathlib import Path

from src.config import get_secret

TIMEOUT = 15

AAVE_SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
SPARK_SUBGRAPH_ID = "GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si"
MORPHO_SUBGRAPH_ID = "8Lz789DP5VKLXumTMTgygjU2xtuzx8AhbaacgN5PYCAs"
MORPHO_BASE_SUBGRAPH_ID = "71ZTy1veF9twER9CLMnPWeLQ7GZcwKsjmygejrgKirqs"
COMPOUND_SUBGRAPH_ID = "5nwMCSHaTqG3Kd2gHznbTXEnZ9QNWsssQfbHhDqQSQFp"

# Aave V3 reserve IDs
AAVE_USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480x2f39d218133afab8f2b819b1066c7e434ad94e9e"
AAVE_USDT = "0xdac17f958d2ee523a2206206994597c13d831ec70x2f39d218133afab8f2b819b1066c7e434ad94e9e"
AAVE_STABLES = {"USDC": AAVE_USDC, "USDT": AAVE_USDT}

# Aave V3 BTC reserves (token addr + pool addr; same pool addr used)
AAVE_POOL = "0x2f39d218133afab8f2b819b1066c7e434ad94e9e"
AAVE_BTC_TOKENS = {
    "WBTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "cbBTC": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
    "LBTC": "0x8236a87084f8b84306f72007f36f2618a5634494",
    "tBTC": "0x18084fba666a33d37592fa2633fd49a74dd93a88",
}

# Spark Lend Ethereum markets
SPARK_STABLES = {
    "USDC": "0x377c3bd93f2a2984e1e7be6a5c22c525ed4a4815",
    "USDT": "0xe7df13b8e3d6740fe17cbe928c7334243d86c92f",
}
SPARK_BTC = {
    "WBTC": "0x4197ba364ae6698015ae5c1468f54087602715b2",
    "cbBTC": "0xb3973d459df38ae57797811f2a1fd061da1bc123",
    "LBTC": "0xa9d4ecebd48c282a70cfd3c469d6c8f178a5738e",
    "tBTC": "0xce6ca9cdce00a2b0c0d1dac93894f4bd2c960567",
}

# Morpho Blue BTC-collateral markets — Ethereum mainnet
MORPHO_MARKETS = {
    "USDC": [
        {"id": "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49", "label": "USDC/WBTC", "btc": "WBTC"},
        {"id": "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64", "label": "USDC/cbBTC", "btc": "cbBTC"},
    ],
    "USDT": [
        {"id": "0xa921ef34e2fc7a27ccc50ae7e4b154e16c9799d3387076c421423ef52ac4df99", "label": "USDT/WBTC", "btc": "WBTC"},
    ],
}

# Morpho Blue BTC-collateral markets — Base
# cbBTC/USDC on Base is by far the largest BTC market in Morpho's ecosystem
# (Coinbase routes its cbBTC borrow flow through here).
MORPHO_BASE_MARKETS = {
    "USDC": [
        {"id": "0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836", "label": "USDC/cbBTC (Base)", "btc": "cbBTC"},
    ],
    # USDT loan markets on Base are negligible; LBTC/tBTC have ~$0 collateral.
}

# Compound V3 Comet proxies
COMPOUND_COMETS = {
    "USDC": "0xc3d688b66703497daa19211eedff47f25384cdc3",
    "USDT": "0x3afdc9bca9213a35503b077a6072f3d0d5ab0840",
}

DATA_DIR = Path(__file__).parent.parent / "data"


def _graph_url(sg: str) -> str | None:
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return None
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{sg}"


def _query(url: str, query: str) -> dict | None:
    for attempt in range(3):
        try:
            resp = requests.post(url, json={"query": query}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                print(f"    Graph errors: {str(data['errors'])[:200]}")
                return None
            return data.get("data")
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


def _btc_price_usd() -> float:
    """Live BTC price from DeFi Llama (snapshot time). Fallback to local CSV."""
    try:
        r = requests.get(
            "https://coins.llama.fi/prices/current/coingecko:bitcoin", timeout=10
        )
        return float(r.json()["coins"]["coingecko:bitcoin"]["price"])
    except Exception:
        pass
    try:
        csv = DATA_DIR / "btc_price.csv"
        if csv.exists():
            df = pd.read_csv(csv)
            df["date"] = pd.to_datetime(df["date"])
            return float(df.sort_values("date").iloc[-1]["btc_price"])
    except Exception:
        pass
    raise RuntimeError("Could not fetch BTC price from any source")


# -------------------- Aave V3 --------------------

RAY = 1e27


def _aave_stables() -> list[dict]:
    """USDC/USDT pool-level liquidity + LIVE rates on Aave V3 Ethereum."""
    url = _graph_url(AAVE_SUBGRAPH_ID)
    if not url:
        return []
    rows = []
    for sym, rid in AAVE_STABLES.items():
        q = f'''{{
          reserve(id: "{rid}") {{
            decimals
            totalLiquidity
            availableLiquidity
            totalCurrentVariableDebt
            utilizationRate
            liquidityRate
            variableBorrowRate
          }}
        }}'''
        data = _query(url, q)
        r = (data or {}).get("reserve")
        if not r:
            continue
        d = int(r["decimals"])
        supply = int(r["totalLiquidity"]) / (10 ** d)
        avail = int(r["availableLiquidity"]) / (10 ** d)
        borrow = int(r["totalCurrentVariableDebt"]) / (10 ** d)
        util = float(r["utilizationRate"]) * 100
        supply_apy = int(r["liquidityRate"]) / RAY * 100
        borrow_apy = int(r["variableBorrowRate"]) / RAY * 100
        rows.append({
            "protocol": "Aave V3",
            "market_label": "pool",
            "symbol": sym,
            "supply_usd": supply,
            "borrow_usd": borrow,
            "available_usd": avail,
            "utilization": util,
            "supply_apy": supply_apy,
            "borrow_apy": borrow_apy,
        })
    return rows


def _aave_btc(btc_price: float) -> list[dict]:
    """BTC collateral sizes (totalLiquidity) on Aave V3."""
    url = _graph_url(AAVE_SUBGRAPH_ID)
    if not url:
        return []
    rows = []
    for sym, token in AAVE_BTC_TOKENS.items():
        rid = token + AAVE_POOL
        q = f'{{ reserve(id: "{rid}") {{ decimals totalLiquidity }} }}'
        data = _query(url, q)
        r = (data or {}).get("reserve")
        if not r:
            continue
        d = int(r["decimals"])
        amount = int(r["totalLiquidity"]) / (10 ** d)
        rows.append({
            "protocol": "Aave V3",
            "btc_symbol": sym,
            "supplied_btc": amount,
            "supplied_usd": amount * btc_price,
        })
    return rows


# -------------------- Spark Lend --------------------

def _spark_stables() -> list[dict]:
    url = _graph_url(SPARK_SUBGRAPH_ID)
    if not url:
        return []
    rows = []
    for sym, mid in SPARK_STABLES.items():
        q = f'''{{
          market(id: "{mid}") {{
            totalDepositBalanceUSD
            totalBorrowBalanceUSD
            rates {{ rate side type }}
          }}
        }}'''
        data = _query(url, q)
        m = (data or {}).get("market")
        if not m:
            continue
        supply = float(m.get("totalDepositBalanceUSD") or 0)
        borrow = float(m.get("totalBorrowBalanceUSD") or 0)
        util = (borrow / supply * 100) if supply > 0 else 0.0
        supply_apy = 0.0
        borrow_apy = 0.0
        for r in m.get("rates", []) or []:
            if r.get("side") == "LENDER" and r.get("type") == "VARIABLE":
                supply_apy = float(r.get("rate") or 0)
            elif r.get("side") == "BORROWER" and r.get("type") == "VARIABLE":
                borrow_apy = float(r.get("rate") or 0)
        rows.append({
            "protocol": "Spark Lend",
            "market_label": "pool",
            "symbol": sym,
            "supply_usd": supply,
            "borrow_usd": borrow,
            "available_usd": supply - borrow,
            "utilization": util,
            "supply_apy": supply_apy,
            "borrow_apy": borrow_apy,
        })
    return rows


def _spark_btc() -> list[dict]:
    url = _graph_url(SPARK_SUBGRAPH_ID)
    if not url:
        return []
    rows = []
    for sym, mid in SPARK_BTC.items():
        q = f'''{{
          market(id: "{mid}") {{
            totalDepositBalanceUSD
            inputToken {{ decimals lastPriceUSD }}
            inputTokenBalance
          }}
        }}'''
        data = _query(url, q)
        m = (data or {}).get("market")
        if not m:
            continue
        supplied_usd = float(m.get("totalDepositBalanceUSD") or 0)
        token = m.get("inputToken") or {}
        decimals = int(token.get("decimals") or 8)
        price = float(token.get("lastPriceUSD") or 0)
        amount = int(m.get("inputTokenBalance") or 0) / (10 ** decimals)
        if supplied_usd == 0 and amount > 0 and price > 0:
            supplied_usd = amount * price
        rows.append({
            "protocol": "Spark Lend",
            "btc_symbol": sym,
            "supplied_btc": amount,
            "supplied_usd": supplied_usd,
        })
    return rows


# -------------------- Morpho Blue --------------------

def _morpho_query(subgraph_id: str, markets_by_loan: dict, btc_price: float,
                  btc_aggregate: dict[str, dict[str, float]]) -> list[dict]:
    """Query a Morpho Blue subgraph (Ethereum OR Base) for the given markets.
    Returns stablecoin pool rows and mutates btc_aggregate in place to sum
    BTC collateral across networks under one "Morpho Blue" protocol bucket.

    The Messari subgraph reports totalDepositBalanceUSD = 0 on Base (price oracle
    not populated), so we always compute BTC USD value client-side via btc_price.
    """
    url = _graph_url(subgraph_id)
    if not url:
        return []
    stable_rows = []

    for sym, markets in markets_by_loan.items():
        for mkt in markets:
            q = f'''{{
              market(id: "{mkt["id"]}") {{
                totalDepositBalanceUSD
                totalBorrowBalanceUSD
                totalCollateral
                rates {{ rate side type }}
              }}
            }}'''
            data = _query(url, q)
            m = (data or {}).get("market")
            if not m:
                continue
            supply = float(m.get("totalDepositBalanceUSD") or 0)
            borrow = float(m.get("totalBorrowBalanceUSD") or 0)
            util = (borrow / supply * 100) if supply > 0 else 0.0
            supply_apy = 0.0
            borrow_apy = 0.0
            for r in m.get("rates", []) or []:
                if r.get("side") == "LENDER" and r.get("type") == "VARIABLE":
                    supply_apy = float(r.get("rate") or 0) * 100
                elif r.get("side") == "BORROWER" and r.get("type") == "VARIABLE":
                    borrow_apy = float(r.get("rate") or 0) * 100
            stable_rows.append({
                "protocol": "Morpho Blue",
                "market_label": mkt["label"],
                "symbol": sym,
                "supply_usd": supply,
                "borrow_usd": borrow,
                "available_usd": supply - borrow,
                "utilization": util,
                "supply_apy": supply_apy,
                "borrow_apy": borrow_apy,
            })

            # BTC collateral: 8 decimals for WBTC/cbBTC/LBTC/tBTC.
            # Compute USD client-side since Base subgraph reports $0 prices.
            btc_sym = mkt["btc"]
            amount = int(m.get("totalCollateral") or 0) / (10 ** 8)
            usd = amount * btc_price
            agg = btc_aggregate.setdefault(btc_sym, {"btc": 0.0, "usd": 0.0})
            agg["btc"] += amount
            agg["usd"] += usd

    return stable_rows


def _morpho_markets(btc_price: float) -> tuple[list[dict], list[dict]]:
    """Aggregate Morpho Blue stats across Ethereum + Base. cbBTC/USDC on Base
    is the largest BTC market in the Morpho ecosystem (Coinbase distribution).
    """
    btc_aggregate: dict[str, dict[str, float]] = {}
    stable_rows = []
    stable_rows += _morpho_query(MORPHO_SUBGRAPH_ID, MORPHO_MARKETS, btc_price, btc_aggregate)
    stable_rows += _morpho_query(MORPHO_BASE_SUBGRAPH_ID, MORPHO_BASE_MARKETS, btc_price, btc_aggregate)

    btc_rows = [
        {"protocol": "Morpho Blue", "btc_symbol": k, "supplied_btc": v["btc"], "supplied_usd": v["usd"]}
        for k, v in btc_aggregate.items()
    ]
    return stable_rows, btc_rows


# -------------------- Compound V3 --------------------

BTC_TOKEN_ADDRESSES = {
    "WBTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "cbBTC": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
    "LBTC": "0x8236a87084f8b84306f72007f36f2618a5634494",
    "tBTC": "0x18084fba666a33d37592fa2633fd49a74dd93a88",
}


def _compound() -> tuple[list[dict], list[dict]]:
    """Compound V3 USDC/USDT comets — pool stables + per-comet BTC collateral."""
    url = _graph_url(COMPOUND_SUBGRAPH_ID)
    if not url:
        return [], []
    stable_rows = []
    btc_aggregate: dict[str, dict[str, float]] = {}

    for sym, comet in COMPOUND_COMETS.items():
        q = f'''{{
          markets(where: {{ cometProxy: "{comet}" }}) {{
            accounting {{
              totalBaseSupplyUsd
              totalBaseBorrowUsd
              utilization
              supplyApr
              borrowApr
            }}
          }}
        }}'''
        data = _query(url, q)
        items = (data or {}).get("markets") or []
        if items:
            a = items[0].get("accounting") or {}
            supply = float(a.get("totalBaseSupplyUsd") or 0)
            borrow = float(a.get("totalBaseBorrowUsd") or 0)
            util = float(a.get("utilization") or 0) * 100
            supply_apy = float(a.get("supplyApr") or 0) * 100
            borrow_apy = float(a.get("borrowApr") or 0) * 100
            stable_rows.append({
                "protocol": "Compound V3",
                "market_label": "pool",
                "symbol": sym,
                "supply_usd": supply,
                "borrow_usd": borrow,
                "available_usd": supply - borrow,
                "utilization": util,
                "supply_apy": supply_apy,
                "borrow_apy": borrow_apy,
            })

        # Latest collateral balance per BTC token (filter by token address)
        for btc_sym, token_addr in BTC_TOKEN_ADDRESSES.items():
            q = f'''{{
              marketCollateralBalances(
                first: 1,
                orderBy: lastUpdateBlockNumber,
                orderDirection: desc,
                where: {{
                  market_: {{ cometProxy: "{comet}" }},
                  collateralToken_: {{ token: "{token_addr}" }}
                }}
              ) {{
                balance
                balanceUsd
                collateralToken {{ token {{ decimals }} }}
              }}
            }}'''
            data = _query(url, q)
            mcbs = (data or {}).get("marketCollateralBalances") or []
            if not mcbs:
                continue
            cb = mcbs[0]
            dec = int((cb.get("collateralToken") or {}).get("token", {}).get("decimals") or 8)
            usd = float(cb.get("balanceUsd") or 0)
            amount = int(cb.get("balance") or 0) / (10 ** dec)
            agg = btc_aggregate.setdefault(btc_sym, {"btc": 0.0, "usd": 0.0})
            agg["btc"] += amount
            agg["usd"] += usd

    btc_rows = [
        {"protocol": "Compound V3", "btc_symbol": k, "supplied_btc": v["btc"], "supplied_usd": v["usd"]}
        for k, v in btc_aggregate.items()
    ]
    return stable_rows, btc_rows


# -------------------- Aggregator --------------------

def fetch_liquidity_snapshot() -> tuple[pd.DataFrame, pd.DataFrame]:
    btc_price = _btc_price_usd()
    print(f"  Using BTC price: ${btc_price:,.0f}")

    stable_rows = []
    btc_rows = []

    print("  [Aave V3] stables + BTC collateral...")
    stable_rows += _aave_stables()
    btc_rows += _aave_btc(btc_price)

    print("  [Spark Lend] stables + BTC collateral...")
    stable_rows += _spark_stables()
    btc_rows += _spark_btc()

    print("  [Morpho Blue] markets + BTC collateral...")
    mst, mbt = _morpho_markets(btc_price)
    stable_rows += mst
    btc_rows += mbt

    print("  [Compound V3] comets + BTC collateral...")
    cst, cbt = _compound()
    stable_rows += cst
    btc_rows += cbt

    stable_df = pd.DataFrame(stable_rows) if stable_rows else pd.DataFrame()
    btc_df = pd.DataFrame(btc_rows) if btc_rows else pd.DataFrame()

    if not stable_df.empty:
        stable_df = stable_df.sort_values(["protocol", "symbol", "market_label"]).reset_index(drop=True)
    if not btc_df.empty:
        btc_df = btc_df.sort_values(["protocol", "btc_symbol"]).reset_index(drop=True)

    return stable_df, btc_df


def fetch_liquidity_snapshot_safe() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        return fetch_liquidity_snapshot()
    except Exception as e:
        print(f"  Liquidity snapshot fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame(), pd.DataFrame()

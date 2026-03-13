"""Fetch current LTV parameters from Aave V3, Morpho Blue, Spark Lend, Compound V3, and Fluid.

For each of the 4 BTC tokens (wBTC, cbBTC, LBTC, tBTC), collects:
- Aave V3: baseLTVasCollateral (max initial LTV) + liquidationThreshold
- Morpho Blue: LLTV per market (= liquidation threshold; no separate initial LTV)
- Spark Lend: maximumLTV + liquidationThreshold
- Compound V3: borrowCollateralFactor + liquidateCollateralFactor
- Fluid: collateralFactor + liquidationThreshold (from vault storage)

Output: data/ltv_comparison.json
"""

import time
import json
import requests
import pandas as pd
from pathlib import Path
from src.config import get_secret

TIMEOUT = 15

# =====================================================================
# Aave V3 Ethereum
# =====================================================================
AAVE_SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
BTC_SYMBOLS_AAVE = ["WBTC", "cbBTC", "tBTC", "LBTC"]

# Display name mapping
AAVE_SYMBOL_TO_TOKEN = {"WBTC": "wBTC", "cbBTC": "cbBTC", "tBTC": "tBTC", "LBTC": "LBTC"}


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


def fetch_aave_ltv() -> list[dict]:
    """Fetch current Aave V3 LTV for BTC collaterals."""
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return []

    url = f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{AAVE_SUBGRAPH_ID}"
    symbols_str = ", ".join(f'"{s}"' for s in BTC_SYMBOLS_AAVE)

    query = f"""{{
      reserves(where: {{ symbol_in: [{symbols_str}] }}) {{
        symbol
        baseLTVasCollateral
        reserveLiquidationThreshold
        borrowingEnabled
        isActive
      }}
    }}"""

    data = _query_graph(url, query)
    if not data or "reserves" not in data:
        return []

    rows = []
    for r in data["reserves"]:
        symbol = r["symbol"]
        token = AAVE_SYMBOL_TO_TOKEN.get(symbol, symbol)
        ltv = float(r.get("baseLTVasCollateral", 0) or 0) / 100  # basis points -> %
        liq = float(r.get("reserveLiquidationThreshold", 0) or 0) / 100

        rows.append({
            "token": token,
            "protocol": "Aave V3",
            "max_ltv": round(ltv, 1),
            "liq_threshold": round(liq, 1),
            "borrowing_enabled": r.get("borrowingEnabled", True),
            "note": "",
        })

    return rows


# =====================================================================
# Morpho Blue Ethereum
# =====================================================================
MORPHO_SUBGRAPH_ID = "8Lz789DP5VKLXumTMTgygjU2xtuzx8AhbaacgN5PYCAs"

# Known BTC collateral markets on Morpho Blue Ethereum
# Format: {loan_token_symbol: [{id, collateral_name}]}
MORPHO_BTC_MARKETS = [
    # WBTC collateral
    {"id": "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49",
     "collateral": "wBTC", "loan": "USDC"},
    {"id": "0xa921ef34e2fc7a27ccc50ae7e4b154e16c9799d3387076c421423ef52ac4df99",
     "collateral": "wBTC", "loan": "USDT"},
    # cbBTC collateral
    {"id": "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64",
     "collateral": "cbBTC", "loan": "USDC"},
]


def fetch_morpho_ltv() -> list[dict]:
    """Fetch Morpho Blue LLTV for BTC collateral markets.

    Morpho Blue doesn't have a separate 'initial LTV' — the LLTV is the
    liquidation threshold. Users can borrow up to LLTV but are immediately
    liquidatable at that level. So effective max LTV ≈ LLTV.
    """
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return []

    url = f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{MORPHO_SUBGRAPH_ID}"

    # Also search for any BTC collateral markets we don't know about
    # by querying markets where the collateral token name contains "BTC"
    discovery_query = """{
      markets(
        first: 50,
        where: { isActive: true }
        orderBy: totalBorrowBalanceUSD
        orderDirection: desc
      ) {
        id
        inputToken { symbol name }
        borrowedToken { symbol name }
        lltv
        totalValueLockedUSD
        totalBorrowBalanceUSD
        isActive
      }
    }"""

    data = _query_graph(url, discovery_query)
    if not data or "markets" not in data:
        return []

    btc_collateral_names = {"wbtc", "cbbtc", "lbtc", "tbtc"}
    stablecoin_loans = {"usdc", "usdt", "dai", "usds", "pyusd"}

    rows = []
    seen = set()

    for m in data["markets"]:
        collateral_symbol = (m.get("inputToken", {}).get("symbol") or "").strip()
        loan_symbol = (m.get("borrowedToken", {}).get("symbol") or "").strip()

        if collateral_symbol.lower() not in btc_collateral_names:
            continue
        if loan_symbol.lower() not in stablecoin_loans:
            continue

        # Deduplicate: take the market with highest TVL per collateral
        dedup_key = (collateral_symbol.lower(), loan_symbol.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        lltv_raw = float(m.get("lltv", 0) or 0)
        # Morpho stores LLTV in WAD (1e18 = 100%)
        lltv_pct = lltv_raw / 1e18 * 100 if lltv_raw > 1 else lltv_raw * 100

        tvl = float(m.get("totalValueLockedUSD", 0) or 0)
        borrows = float(m.get("totalBorrowBalanceUSD", 0) or 0)

        # Normalize token display
        token_display = collateral_symbol
        if token_display == "WBTC":
            token_display = "wBTC"

        rows.append({
            "token": token_display,
            "protocol": "Morpho Blue",
            "max_ltv": round(lltv_pct, 1),
            "liq_threshold": round(lltv_pct, 1),  # Same as LLTV in Morpho
            "borrowing_enabled": True,
            "note": f"Borrow {loan_symbol}, TVL ${tvl/1e6:.0f}M",
        })

    return rows


# =====================================================================
# Spark Lend Ethereum (via Etherscan eth_call to PoolDataProvider)
# =====================================================================
# Spark Lend is an Aave V3 fork — uses the same PoolDataProvider interface.
# PoolDataProvider: 0xFc21d6d146E6086B8359705C8b28512a983db0cb
SPARK_POOL_DATA_PROVIDER = "0xFc21d6d146E6086B8359705C8b28512a983db0cb"

SPARK_BTC_TOKENS = {
    "wBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "cbBTC": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",
    "LBTC": "0x8236a87084f8B84306f72007F36F2618A5634494",
    "tBTC": "0x18084fbA666a33d37592fA2633fD49a74DD93a88",
}


def fetch_spark_ltv() -> list[dict]:
    """Fetch Spark Lend LTV via Etherscan eth_call to PoolDataProvider.

    Calls getReserveConfigurationData(address) which returns:
    (decimals, ltv, liquidationThreshold, liquidationBonus, reserveFactor,
     usageAsCollateralEnabled, borrowingEnabled, stableBorrowRateEnabled, isActive, isFrozen)

    LTV and liquidationThreshold are in basis points (e.g. 7300 = 73%).
    """
    etherscan_key = get_secret("ETHERSCAN_API_KEY")
    if not etherscan_key:
        return []

    rows = []
    for token, addr in SPARK_BTC_TOKENS.items():
        try:
            # getReserveConfigurationData(address) selector: 0x3e150141
            padded = addr[2:].lower().zfill(64)
            calldata = "0x3e150141" + padded

            resp = requests.get(
                "https://api.etherscan.io/v2/api",
                params={
                    "chainid": "1",
                    "module": "proxy",
                    "action": "eth_call",
                    "to": SPARK_POOL_DATA_PROVIDER,
                    "data": calldata,
                    "tag": "latest",
                    "apikey": etherscan_key,
                },
                timeout=TIMEOUT,
            )
            result = resp.json().get("result", "0x")

            if not result or not result.startswith("0x") or len(result) < 66:
                continue

            hex_data = result[2:]
            vals = [int(hex_data[i * 64:(i + 1) * 64], 16) for i in range(10)]

            ltv = vals[1] / 100  # basis points -> %
            liq_threshold = vals[2] / 100
            collateral_enabled = vals[5] == 1
            borrowing_enabled = vals[6] == 1
            is_active = vals[8] == 1

            if not is_active or not collateral_enabled:
                continue

            rows.append({
                "token": token,
                "protocol": "Spark Lend",
                "max_ltv": round(ltv, 1),
                "liq_threshold": round(liq_threshold, 1),
                "borrowing_enabled": borrowing_enabled,
                "note": "",
            })
        except Exception as e:
            print(f"    Spark {token} failed: {e}")

    return rows


# =====================================================================
# Compound V3 (Comet) via The Graph
# =====================================================================
COMPOUND_SUBGRAPH_ID = "5nwMCSHaTqG3Kd2gHznbTXEnZ9QNWsssQfbHhDqQSQFp"

BTC_SYMBOL_NORMALIZE = {"WBTC": "wBTC", "cbBTC": "cbBTC", "LBTC": "LBTC", "tBTC": "tBTC"}
STABLECOIN_BASES = {"usdc", "usdt", "dai", "usds", "pyusd"}


def fetch_compound_ltv() -> list[dict]:
    """Fetch Compound V3 borrowCollateralFactor for BTC collateral tokens.

    Each Compound V3 market (USDC, USDT, etc.) has separate collateral configs.
    borrowCollateralFactor = max LTV, liquidateCollateralFactor = liq threshold.
    Stored as decimals (0.80 = 80%) in the Paperclip Labs subgraph.
    """
    key = get_secret("THEGRAPH_API_KEY")
    if not key:
        return []

    url = f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{COMPOUND_SUBGRAPH_ID}"

    query = """{
      collateralTokens(
        first: 50,
        where: { token_: { symbol_in: ["WBTC", "cbBTC", "LBTC", "tBTC"] } }
      ) {
        token { symbol }
        market {
          configuration {
            baseToken { token { symbol } }
          }
        }
        borrowCollateralFactor
        liquidateCollateralFactor
      }
    }"""

    data = _query_graph(url, query)
    if not data or "collateralTokens" not in data:
        return []

    best_by_token: dict[str, dict] = {}

    for ct in data["collateralTokens"]:
        symbol_raw = (ct.get("token", {}).get("symbol") or "").strip()
        if symbol_raw not in BTC_SYMBOL_NORMALIZE:
            continue
        token = BTC_SYMBOL_NORMALIZE[symbol_raw]

        base_symbol = ""
        try:
            base_symbol = ct["market"]["configuration"]["baseToken"]["token"]["symbol"]
        except (KeyError, TypeError):
            pass
        if base_symbol.lower() not in STABLECOIN_BASES:
            continue

        bcf = float(ct.get("borrowCollateralFactor", 0) or 0)
        lcf = float(ct.get("liquidateCollateralFactor", 0) or 0)

        ltv_pct = bcf * 100
        liq_pct = lcf * 100

        if ltv_pct <= 0:
            continue

        row = {
            "token": token,
            "protocol": "Compound V3",
            "max_ltv": round(ltv_pct, 1),
            "liq_threshold": round(liq_pct, 1),
            "borrowing_enabled": True,
            "note": f"Borrow {base_symbol}",
        }

        if token not in best_by_token or ltv_pct > best_by_token[token]["max_ltv"]:
            best_by_token[token] = row

    return list(best_by_token.values())


# =====================================================================
# Fluid (via Etherscan eth_call to FluidVaultResolver)
# =====================================================================
# FluidVaultResolver.getVaultEntireData(address) returns a complex struct.
# Config section identified by two consecutive 10000 values (rate magnifiers),
# followed by: collateralFactor, liquidationThreshold, liquidationMaxLimit, ...
# All config values in basis points (0-10000 = 0-100%).
FLUID_VAULT_RESOLVER = "0xA5C3E16523eeeDDcC34706b0E6bE88b4c6EA95cC"

# Known BTC collateral vaults on Fluid Ethereum
FLUID_BTC_VAULTS = [
    {"vault": "0x6f72895cf6904489bcd862c941c3d02a3ee4f03e", "collateral": "wBTC", "loan": "USDC"},
    {"vault": "0x3a0b7c8840d74d39552ef53f586dd8c3d1234c40", "collateral": "wBTC", "loan": "USDT"},
]


def _keccak256(data: bytes) -> bytes:
    """Compute keccak256 hash. Uses pycryptodome if available, else skips."""
    try:
        from Crypto.Hash import keccak
        k = keccak.new(digest_bits=256)
        k.update(data)
        return bytes.fromhex(k.hexdigest())
    except ImportError:
        return b""


def fetch_fluid_ltv() -> list[dict]:
    """Fetch Fluid vault LTV via FluidVaultResolver.getVaultEntireData().

    Calls the resolver for each known BTC vault and parses the ABI-encoded
    response to extract collateralFactor and liquidationThreshold.
    """
    etherscan_key = get_secret("ETHERSCAN_API_KEY")
    if not etherscan_key:
        return []

    selector_bytes = _keccak256(b"getVaultEntireData(address)")
    if not selector_bytes:
        print("    Fluid: pycryptodome not installed, skipping")
        return []
    selector = selector_bytes[:4].hex()

    best_by_token: dict[str, dict] = {}

    for vault_info in FLUID_BTC_VAULTS:
        try:
            padded = vault_info["vault"][2:].lower().zfill(64)
            calldata = "0x" + selector + padded

            resp = requests.get(
                "https://api.etherscan.io/v2/api",
                params={
                    "chainid": "1",
                    "module": "proxy",
                    "action": "eth_call",
                    "to": FLUID_VAULT_RESOLVER,
                    "data": calldata,
                    "tag": "latest",
                    "apikey": etherscan_key,
                },
                timeout=TIMEOUT,
            )
            result = resp.json().get("result", "0x")

            if not result or len(result) < 66:
                continue

            hex_data = result[2:]
            n_words = len(hex_data) // 64
            words = [int(hex_data[i * 64:(i + 1) * 64], 16) for i in range(min(n_words, 50))]

            # Find config section: two consecutive 10000 (rate magnifiers) followed
            # by a reasonable collateralFactor (5000-10000).
            ltv_pct = 0
            liq_pct = 0
            for i in range(len(words) - 4):
                if words[i] == 10000 and words[i + 1] == 10000 and 5000 <= words[i + 2] <= 10000:
                    ltv_pct = words[i + 2] / 100
                    liq_pct = words[i + 3] / 100
                    break

            if ltv_pct <= 0:
                continue

            token = vault_info["collateral"]
            row = {
                "token": token,
                "protocol": "Fluid",
                "max_ltv": round(ltv_pct, 1),
                "liq_threshold": round(liq_pct, 1),
                "borrowing_enabled": True,
                "note": f"Borrow {vault_info['loan']}",
            }

            if token not in best_by_token or ltv_pct > best_by_token[token]["max_ltv"]:
                best_by_token[token] = row

        except Exception as e:
            print(f"    Fluid {vault_info['collateral']}/{vault_info['loan']} failed: {e}")

    return list(best_by_token.values())


# =====================================================================
# Combined
# =====================================================================

def fetch_ltv_comparison() -> list[dict]:
    """Fetch LTV comparison from all protocols."""
    print("  Fetching Aave V3 LTV...")
    aave = fetch_aave_ltv()
    print(f"    Got {len(aave)} Aave entries")

    print("  Fetching Morpho Blue LLTV...")
    morpho = fetch_morpho_ltv()
    print(f"    Got {len(morpho)} Morpho entries")

    print("  Fetching Spark Lend LTV...")
    spark = fetch_spark_ltv()
    print(f"    Got {len(spark)} Spark entries")

    print("  Fetching Compound V3 LTV...")
    compound = fetch_compound_ltv()
    print(f"    Got {len(compound)} Compound entries")

    print("  Fetching Fluid LTV...")
    fluid = fetch_fluid_ltv()
    print(f"    Got {len(fluid)} Fluid entries")

    return aave + morpho + spark + compound + fluid


def fetch_ltv_comparison_safe() -> list[dict]:
    """Wrapper that never crashes."""
    try:
        return fetch_ltv_comparison()
    except Exception as e:
        print(f"  LTV comparison fetch failed: {e}")
        return []

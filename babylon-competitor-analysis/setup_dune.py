"""Create Dune queries via API, execute them, save results to data/dune.csv.

Usage:
    uv run python setup_dune.py

This script:
1. Creates 3 SQL queries on your Dune account via the API
2. Executes each query
3. Saves combined results to data/dune.csv
4. Prints query IDs for reference (optional: save to config.py)
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).parent.parent / ".env")

API_KEY = os.environ.get("DUNE_API_KEY")
BASE = "https://api.dune.com/api/v1"
HEADERS = {"X-Dune-API-Key": API_KEY, "Content-Type": "application/json"}

# Our tracked BTC token addresses on Ethereum mainnet
TOKEN_ADDRESSES = [
    "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # wBTC
    "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",  # cbBTC
    "0x18084fbA666a33d37592fA2633fD49a74DD93a88",  # tBTC
    "0x8236a87084f8B84306f72007F36F2618A5634494",  # LBTC
    "0x7A56E1C57C7475CCf65CfbCd7E7c62F694d313A4",  # SolvBTC
]

ADDR_LIST_SQL = ", ".join(f"0x{a[2:]}" for a in TOKEN_ADDRESSES)

# --- SQL Queries ---

HOLDER_COUNT_SQL = f"""
-- BTC wrapper token holder counts on Ethereum
-- Counts addresses with positive balance from transfer events (net receivers)
WITH transfers AS (
    SELECT
        contract_address,
        "to" AS address,
        CAST(value AS DOUBLE) AS amount
    FROM erc20_ethereum.evt_Transfer
    WHERE contract_address IN ({ADDR_LIST_SQL})

    UNION ALL

    SELECT
        contract_address,
        "from" AS address,
        -CAST(value AS DOUBLE) AS amount
    FROM erc20_ethereum.evt_Transfer
    WHERE contract_address IN ({ADDR_LIST_SQL})
),
balances AS (
    SELECT
        contract_address,
        address,
        SUM(amount) AS balance
    FROM transfers
    WHERE address != 0x0000000000000000000000000000000000000000
    GROUP BY contract_address, address
    HAVING SUM(amount) > 0
)
SELECT
    CAST(contract_address AS VARCHAR) AS contract_address,
    COUNT(*) AS holder_count
FROM balances
GROUP BY contract_address
"""

ACTIVE_ADDRESSES_SQL = f"""
-- Daily active addresses (last 30 days) for BTC wrapper tokens
SELECT
    CAST(contract_address AS VARCHAR) AS contract_address,
    DATE_TRUNC('day', evt_block_time) AS day,
    COUNT(DISTINCT "from") + COUNT(DISTINCT "to") AS daily_active
FROM erc20_ethereum.evt_Transfer
WHERE contract_address IN ({ADDR_LIST_SQL})
    AND evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY contract_address, DATE_TRUNC('day', evt_block_time)
"""

BRIDGE_VOLUME_SQL = f"""
-- Mint volume (30d) for BTC wrapper tokens
-- Mints = transfers from 0x0 address
SELECT
    CAST(contract_address AS VARCHAR) AS contract_address,
    SUM(CAST(value AS DOUBLE) / 1e8) AS total_minted_btc,
    SUM(CAST(value AS DOUBLE) / 1e8 * p.price) AS total_minted_usd
FROM erc20_ethereum.evt_Transfer t
LEFT JOIN prices.usd_latest p
    ON p.blockchain = 'ethereum'
    AND p.contract_address = t.contract_address
WHERE t.contract_address IN ({ADDR_LIST_SQL})
    AND t."from" = 0x0000000000000000000000000000000000000000
    AND t.evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY t.contract_address
"""

QUERIES = {
    "holders": ("Babylon CI - BTC Token Holder Counts", HOLDER_COUNT_SQL),
    "active_addresses": ("Babylon CI - BTC Token Active Addresses 30d", ACTIVE_ADDRESSES_SQL),
    "bridge_volume": ("Babylon CI - BTC Token Bridge Volume 30d", BRIDGE_VOLUME_SQL),
}


def create_query(name: str, sql: str) -> int | None:
    """Create a query on Dune. Returns query_id."""
    resp = requests.post(
        f"{BASE}/query",
        headers=HEADERS,
        json={"name": name, "query_sql": sql, "is_private": True},
        timeout=15,
    )
    if resp.status_code == 200:
        qid = resp.json().get("query_id")
        print(f"  Created query '{name}' -> ID {qid}")
        return qid
    else:
        print(f"  Failed to create query '{name}': {resp.status_code} {resp.text[:200]}")
        return None


def execute_query(query_id: int) -> list[dict]:
    """Execute a query and wait for results."""
    # Try cached first
    try:
        resp = requests.get(
            f"{BASE}/query/{query_id}/results",
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            rows = resp.json().get("result", {}).get("rows", [])
            if rows:
                print(f"  Query {query_id}: got {len(rows)} cached rows")
                return rows
    except Exception:
        pass

    # Execute fresh
    print(f"  Query {query_id}: executing...")
    resp = requests.post(
        f"{BASE}/query/{query_id}/execute",
        headers=HEADERS,
        json={},
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        print(f"  Execute failed: {resp.status_code} {resp.text[:200]}")
        return []

    execution_id = resp.json().get("execution_id")
    if not execution_id:
        print("  No execution_id returned")
        return []

    # Poll
    waited = 0
    while waited < 120:
        time.sleep(3)
        waited += 3
        try:
            status_resp = requests.get(
                f"{BASE}/execution/{execution_id}/status",
                headers=HEADERS,
                timeout=10,
            )
            state = status_resp.json().get("state", "")
            if state == "QUERY_STATE_COMPLETED":
                results_resp = requests.get(
                    f"{BASE}/execution/{execution_id}/results",
                    headers=HEADERS,
                    timeout=15,
                )
                rows = results_resp.json().get("result", {}).get("rows", [])
                print(f"  Query {query_id}: completed, {len(rows)} rows")
                return rows
            elif state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED", "QUERY_STATE_EXPIRED"):
                print(f"  Query {query_id}: {state}")
                return []
            else:
                if waited % 15 == 0:
                    print(f"  Query {query_id}: {state} ({waited}s)...")
        except Exception as e:
            print(f"  Poll error: {e}")

    print(f"  Query {query_id}: timeout after {waited}s")
    return []


def main():
    if not API_KEY:
        print("ERROR: DUNE_API_KEY not set in .env")
        sys.exit(1)

    print("=" * 60)
    print("Dune Analytics — Query Setup & Data Collection")
    print("=" * 60)

    query_ids = {}

    # Step 1: Create queries
    print("\n[Step 1] Creating queries on Dune...")
    for key, (name, sql) in QUERIES.items():
        qid = create_query(name, sql)
        if qid:
            query_ids[key] = qid
        else:
            print(f"  SKIPPING {key} — could not create query")

    if not query_ids:
        print("\nERROR: No queries created. Check your API key permissions.")
        print("You may need a Dune Plus plan for the Query API.")
        print("\nAlternative: create queries manually on dune.com with the SQL below,")
        print("then set query IDs in src/config.py -> DUNE_QUERIES")
        for key, (name, sql) in QUERIES.items():
            print(f"\n--- {key}: {name} ---")
            print(sql)
        sys.exit(1)

    # Step 2: Execute queries and collect data
    print("\n[Step 2] Executing queries...")
    all_data = {}  # {address: {metric: value}}

    # Holders
    if "holders" in query_ids:
        print("\n  Fetching holder counts...")
        rows = execute_query(query_ids["holders"])
        for row in rows:
            addr = row.get("contract_address", "").lower()
            all_data.setdefault(addr, {})["holders_count"] = row.get("holder_count", 0)

    # Active addresses
    if "active_addresses" in query_ids:
        print("\n  Fetching active addresses...")
        rows = execute_query(query_ids["active_addresses"])
        from collections import defaultdict
        daily_counts = defaultdict(list)
        for row in rows:
            addr = row.get("contract_address", "").lower()
            daily_counts[addr].append(row.get("daily_active", 0))
        for addr, counts in daily_counts.items():
            avg = sum(counts) / len(counts) if counts else 0
            all_data.setdefault(addr, {})["daily_active_addresses_avg"] = round(avg)

    # Bridge volume
    if "bridge_volume" in query_ids:
        print("\n  Fetching bridge volume...")
        rows = execute_query(query_ids["bridge_volume"])
        for row in rows:
            addr = row.get("contract_address", "").lower()
            all_data.setdefault(addr, {})["bridge_volume_30d_usd"] = row.get("total_minted_usd", 0)
            all_data.setdefault(addr, {})["bridge_volume_30d_btc"] = row.get("total_minted_btc", 0)

    # Step 3: Save results
    if all_data:
        import pandas as pd
        result_rows = []
        for addr, metrics in all_data.items():
            metrics["dune_token_address"] = addr
            result_rows.append(metrics)
        df = pd.DataFrame(result_rows)

        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)
        df.to_csv(data_dir / "dune.csv", index=False)
        print(f"\n  Saved {len(df)} tokens to data/dune.csv")
        print(df.to_string(index=False))
    else:
        print("\n  WARNING: No data collected from Dune queries")

    # Step 4: Print query IDs for config.py
    print("\n" + "=" * 60)
    print("Query IDs (add to src/config.py -> DUNE_QUERIES):")
    print(f'DUNE_QUERIES = {{')
    for key in ["holders", "active_addresses", "bridge_volume"]:
        qid = query_ids.get(key)
        print(f'    "{key}": {qid},')
    print(f'}}')
    print("=" * 60)


if __name__ == "__main__":
    main()

"""Fetch on-chain analytics from Dune. Requires DUNE_API_KEY."""

import time
import requests
import pandas as pd
from src.config import get_secret, DUNE_QUERIES

BASE_URL = "https://api.dune.com/api/v1"
TIMEOUT = 10
POLL_INTERVAL = 2
POLL_MAX_WAIT = 60


def _headers() -> dict:
    key = get_secret("DUNE_API_KEY")
    return {"X-Dune-API-Key": key} if key else {}


def _get_cached_results(query_id: int) -> list[dict] | None:
    """Try to get latest cached results (cheap, no execution credits)."""
    try:
        resp = requests.get(
            f"{BASE_URL}/query/{query_id}/results",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        return result.get("rows", [])
    except Exception:
        return None


def _execute_and_poll(query_id: int, params: dict | None = None) -> list[dict] | None:
    """Execute a query and poll for results."""
    try:
        body = {}
        if params:
            body["query_parameters"] = params

        resp = requests.post(
            f"{BASE_URL}/query/{query_id}/execute",
            headers=_headers(),
            json=body,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        execution_id = resp.json().get("execution_id")
        if not execution_id:
            return None

        # Poll for completion
        waited = 0
        while waited < POLL_MAX_WAIT:
            time.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL

            status_resp = requests.get(
                f"{BASE_URL}/execution/{execution_id}/status",
                headers=_headers(),
                timeout=TIMEOUT,
            )
            status_resp.raise_for_status()
            state = status_resp.json().get("state")

            if state == "QUERY_STATE_COMPLETED":
                results_resp = requests.get(
                    f"{BASE_URL}/execution/{execution_id}/results",
                    headers=_headers(),
                    timeout=TIMEOUT,
                )
                results_resp.raise_for_status()
                return results_resp.json().get("result", {}).get("rows", [])
            elif state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"):
                return None

        return None  # Timeout
    except Exception:
        return None


def fetch_dune_query(query_id: int, params: dict | None = None) -> list[dict]:
    """Fetch results for a Dune query. Tries cached first, then executes."""
    if not query_id:
        return []

    rows = _get_cached_results(query_id)
    if rows is not None:
        return rows

    rows = _execute_and_poll(query_id, params)
    return rows or []


def fetch_dune() -> pd.DataFrame:
    """Fetch all Dune data. Returns empty DataFrame if no API key or no query IDs."""
    api_key = get_secret("DUNE_API_KEY")
    if not api_key:
        return pd.DataFrame()

    # Check if any query IDs are configured
    if not any(DUNE_QUERIES.values()):
        return pd.DataFrame()

    all_data = {}

    # Holders
    holders_qid = DUNE_QUERIES.get("holders")
    if holders_qid:
        rows = fetch_dune_query(holders_qid)
        for row in rows:
            addr = row.get("contract_address", "").lower()
            all_data.setdefault(addr, {})["holders_count"] = row.get("holder_count", 0)

    # Active addresses
    active_qid = DUNE_QUERIES.get("active_addresses")
    if active_qid:
        rows = fetch_dune_query(active_qid)
        # Average daily active across days per contract
        from collections import defaultdict
        daily_counts = defaultdict(list)
        for row in rows:
            addr = row.get("contract_address", "").lower()
            daily_counts[addr].append(row.get("daily_active", 0))
        for addr, counts in daily_counts.items():
            avg = sum(counts) / len(counts) if counts else 0
            all_data.setdefault(addr, {})["daily_active_addresses_avg"] = round(avg)

    # Bridge volume
    bridge_qid = DUNE_QUERIES.get("bridge_volume")
    if bridge_qid:
        rows = fetch_dune_query(bridge_qid)
        for row in rows:
            addr = row.get("contract_address", "").lower()
            all_data.setdefault(addr, {})["bridge_volume_30d_usd"] = row.get("total_minted_usd", 0)
            all_data.setdefault(addr, {})["bridge_volume_30d_btc"] = row.get("total_minted_btc", 0)

    if not all_data:
        return pd.DataFrame()

    result_rows = []
    for addr, metrics in all_data.items():
        metrics["dune_token_address"] = addr
        result_rows.append(metrics)

    return pd.DataFrame(result_rows)


def fetch_dune_safe() -> pd.DataFrame:
    """Wrapper that never crashes."""
    try:
        return fetch_dune()
    except Exception as e:
        print(f"Dune fetch failed: {e}")
        return pd.DataFrame()

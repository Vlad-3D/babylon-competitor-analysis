"""Collect data from all APIs and save to data/ for static dashboard deployment."""

import os
import sys
from pathlib import Path

# Load .env before any src imports (for API keys)
from dotenv import load_dotenv
load_dotenv()
# Also try parent dir .env
load_dotenv(Path(__file__).parent.parent / ".env")

from src.config import COMPETITORS
from src.fetch_defillama import fetch_defillama_safe
from src.fetch_coingecko import fetch_coingecko_safe
from src.fetch_defi_yields import fetch_defi_yields_safe
from src.fetch_thegraph import fetch_thegraph_safe
from src.fetch_dune import fetch_dune_safe
from src.fetch_aave_rates import fetch_aave_rates_safe, fetch_btc_price_safe
from src.fetch_aave_btc_borrow import fetch_aave_btc_borrow_safe
from src.fetch_spark_btc import fetch_spark_btc_safe, fetch_spark_stable_safe
from src.fetch_ltv_comparison import fetch_ltv_comparison_safe
from src.fetch_morpho_btc_borrow import fetch_morpho_btc_borrow_safe
from src.fetch_maple_btc_borrow import fetch_maple_btc_borrow_safe
from src.fetch_compound_btc_borrow import fetch_compound_btc_borrow_safe
from src.fetch_reserve_factor import fetch_reserve_factor_safe
from src.fetch_liquidity_snapshot import fetch_liquidity_snapshot_safe

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def main():
    print("=" * 60)
    print("Babylon TBV — Data Collection")
    print("=" * 60)

    # Determine what to collect
    collect_all = len(sys.argv) < 2
    targets = set(sys.argv[1:]) if not collect_all else set()

    # 1. DeFi Llama
    print("\n[1/11] DeFi Llama TVL...")
    slugs = [c["defillama_slug"] for c in COMPETITORS if c.get("defillama_slug")]
    defillama_df = fetch_defillama_safe(slugs)
    if defillama_df.empty:
        print("  WARNING: No DeFi Llama data returned")
    else:
        defillama_df.to_json(DATA_DIR / "defillama.json", orient="records", indent=2)
        print(f"  Saved {len(defillama_df)} protocols to data/defillama.json")

    # 2. CoinGecko (for tokens DeFi Llama doesn't track, e.g. cbBTC)
    print("\n[2/11] CoinGecko market cap...")
    coin_ids = {c["name"]: c["coingecko_id"] for c in COMPETITORS if c.get("coingecko_id")}
    if coin_ids:
        coingecko_df = fetch_coingecko_safe(coin_ids)
        if coingecko_df.empty:
            print("  WARNING: No CoinGecko data returned")
        else:
            coingecko_df.to_json(DATA_DIR / "coingecko.json", orient="records", indent=2)
            print(f"  Saved {len(coingecko_df)} tokens to data/coingecko.json")
    else:
        print("  SKIPPED: No competitors with coingecko_id configured")

    # 3. DeFi Yields
    print("\n[3/11] DeFi Yields (integrations)...")
    yields_df = fetch_defi_yields_safe()
    if yields_df.empty:
        print("  WARNING: No DeFi Yields data returned")
    else:
        yields_df.to_json(DATA_DIR / "defi_yields.json", orient="records", indent=2)
        print(f"  Saved {len(yields_df)} assets to data/defi_yields.json")

    # 4. The Graph (Aave V3 reserves snapshot)
    print("\n[4/11] The Graph (Aave V3 reserves)...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        graph_df = fetch_thegraph_safe()
        if graph_df.empty:
            print("  WARNING: No Graph data returned")
        else:
            graph_df.to_csv(DATA_DIR / "thegraph.csv", index=False)
            print(f"  Saved {len(graph_df)} reserves to data/thegraph.csv")

    # 5. Dune Analytics
    print("\n[5/11] Dune Analytics...")
    dune_key = os.environ.get("DUNE_API_KEY")
    if not dune_key:
        print("  SKIPPED: DUNE_API_KEY not set")
    else:
        dune_df = fetch_dune_safe()
        if dune_df.empty:
            print("  WARNING: No Dune data returned (query IDs may not be configured)")
        else:
            dune_df.to_csv(DATA_DIR / "dune.csv", index=False)
            print(f"  Saved {len(dune_df)} tokens to data/dune.csv")

    # 6. Aave V3 BTC Borrow Rates (Ethereum + Base — weekly, 2 years)
    print("\n[6/11] Aave V3 BTC Borrow Rates (ETH + Base)...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        btc_borrow_df = fetch_aave_btc_borrow_safe()
        if btc_borrow_df.empty:
            print("  WARNING: No BTC borrow rate data returned")
        else:
            btc_borrow_df.to_csv(DATA_DIR / "aave_btc_borrow.csv", index=False)
            print(f"  Saved {len(btc_borrow_df)} data points to data/aave_btc_borrow.csv")

    # 7. Aave V3 Rate History (The Graph — weekly snapshots, 2 years)
    print("\n[7/11] Aave V3 Rate History (The Graph)...")
    rates_df = fetch_aave_rates_safe()
    if rates_df.empty:
        print("  WARNING: No Aave rate history returned")
    else:
        rates_df.to_csv(DATA_DIR / "aave_rates.csv", index=False)
        print(f"  Saved {len(rates_df)} weekly data points to data/aave_rates.csv")

    # 8. BTC Price History (DeFi Llama — weekly, 2 years)
    print("\n[8/11] BTC Price History...")
    btc_df = fetch_btc_price_safe()
    if btc_df.empty:
        print("  WARNING: No BTC price data returned")
    else:
        btc_df.to_csv(DATA_DIR / "btc_price.csv", index=False)
        print(f"  Saved {len(btc_df)} weekly prices to data/btc_price.csv")

    # 9. Morpho Blue BTC Borrow Rates (Ethereum — weekly from daily snapshots)
    print("\n[9/11] Morpho Blue BTC Borrow Rates...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        morpho_df = fetch_morpho_btc_borrow_safe()
        if morpho_df.empty:
            print("  WARNING: No Morpho BTC rate data returned")
        else:
            morpho_df.to_csv(DATA_DIR / "morpho_btc_borrow.csv", index=False)
            print(f"  Saved {len(morpho_df)} data points to data/morpho_btc_borrow.csv")

    # 10. Spark Lend BTC Borrow Rates (The Graph — daily snapshots, 2 years)
    print("\n[10/11] Spark Lend BTC Borrow Rates...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        spark_df = fetch_spark_btc_safe()
        if spark_df.empty:
            print("  WARNING: No Spark BTC rate data returned")
        else:
            spark_df.to_csv(DATA_DIR / "spark_btc.csv", index=False)
            print(f"  Saved {len(spark_df)} data points to data/spark_btc.csv")

    # 11. Spark Lend Stablecoin Borrow Rates (USDC/USDT/DAI/USDS — borrowing against BTC)
    print("\n[11/11] Spark Lend Stablecoin Borrow Rates...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        spark_stable_df = fetch_spark_stable_safe()
        if spark_stable_df.empty:
            print("  WARNING: No Spark stablecoin rate data returned")
        else:
            spark_stable_df.to_csv(DATA_DIR / "spark_stable.csv", index=False)
            print(f"  Saved {len(spark_stable_df)} data points to data/spark_stable.csv")

    # 12. Maple Finance Lending Yields (DefiLlama)
    print("\n[12/13] Maple Finance Lending Yields...")
    maple_df = fetch_maple_btc_borrow_safe()
    if maple_df.empty:
        print("  WARNING: No Maple lending yield data returned")
    else:
        maple_df.to_csv(DATA_DIR / "maple_btc_borrow.csv", index=False)
        print(f"  Saved {len(maple_df)} data points to data/maple_btc_borrow.csv")

    # 13. Compound V3 Borrow Rates (The Graph)
    print("\n[13/14] Compound V3 Borrow Rates...")
    compound_df = fetch_compound_btc_borrow_safe()
    if compound_df.empty:
        print("  WARNING: No Compound V3 borrow rate data returned")
    else:
        compound_df.to_csv(DATA_DIR / "compound_btc_borrow.csv", index=False)
        print(f"  Saved {len(compound_df)} data points to data/compound_btc_borrow.csv")

    # 14. LTV Comparison (Aave + Morpho + Spark)
    print("\n[14/14] LTV Comparison (Aave + Morpho + Spark)...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        import json as _json
        ltv_data = fetch_ltv_comparison_safe()
        if not ltv_data:
            print("  WARNING: No LTV comparison data returned")
        else:
            with open(DATA_DIR / "ltv_comparison.json", "w") as f:
                _json.dump(ltv_data, f, indent=2)
            print(f"  Saved {len(ltv_data)} entries to data/ltv_comparison.json")

    # 15. Reserve Factor (monthly, since inception)
    print("\n[15/16] Reserve Factor history (Aave/Spark/Morpho/Compound)...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        rf_df = fetch_reserve_factor_safe()
        if rf_df.empty:
            print("  WARNING: No reserve factor data returned")
        else:
            rf_df.to_csv(DATA_DIR / "reserve_factor.csv", index=False)
            print(f"  Saved {len(rf_df)} monthly points to data/reserve_factor.csv")

    # 16. Liquidity Snapshot — current utilization, available liquidity, BTC collateral
    print("\n[16/16] Liquidity Snapshot (USDC/USDT pools + BTC collateral)...")
    api_key = os.environ.get("THEGRAPH_API_KEY")
    if not api_key:
        print("  SKIPPED: THEGRAPH_API_KEY not set")
    else:
        stable_df, btc_df = fetch_liquidity_snapshot_safe()
        if stable_df.empty and btc_df.empty:
            print("  WARNING: No liquidity snapshot data returned")
        else:
            if not stable_df.empty:
                stable_df.to_csv(DATA_DIR / "liquidity_stablecoin.csv", index=False)
                print(f"  Saved {len(stable_df)} stablecoin pool rows to data/liquidity_stablecoin.csv")
            if not btc_df.empty:
                btc_df.to_csv(DATA_DIR / "liquidity_btc_collateral.csv", index=False)
                print(f"  Saved {len(btc_df)} BTC collateral rows to data/liquidity_btc_collateral.csv")

    # Summary
    print("\n" + "=" * 60)
    print("Files in data/:")
    for f in sorted(DATA_DIR.iterdir()):
        if f.name.startswith("."):
            continue
        size = f.stat().st_size
        print(f"  {f.name:25s} {size:>10,} bytes")
    print("=" * 60)
    print("Done. Dashboard can now run from static files.")


if __name__ == "__main__":
    main()

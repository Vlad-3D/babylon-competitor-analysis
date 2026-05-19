"""Spark Lend — Stablecoin Borrow Rates (USDC/USDT/DAI/USDS) against BTC collateral."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="Spark Lend", page_icon="⚡", layout="wide")

from src.auth import check_password
check_password()

from src.ui_helpers import average_rate_summary, reserve_factor_tab, liquidity_tab

DATA_DIR = Path(__file__).parent.parent / "data"

st.title("Spark Lend — USDC/USDT/DAI/USDS against BTC")
st.caption("Borrow rates for stablecoins on Spark Lend, collateralised by WBTC/cbBTC/LBTC/tBTC.")


@st.cache_data(ttl=300)
def load_spark() -> pd.DataFrame:
    p = DATA_DIR / "spark_stable.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, parse_dates=["date"])
    df = df.rename(columns={"borrow_rate": "borrow_apy", "supply_rate": "supply_apy"})
    return df


@st.cache_data(ttl=300)
def load_btc() -> pd.DataFrame:
    p = DATA_DIR / "btc_price.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


df = load_spark()
btc_df = load_btc()

if df.empty:
    st.error("No Spark rate data found. Run `uv run python collect_data.py`.")
    st.stop()

SYMBOLS = ["USDC", "USDT", "DAI", "USDS"]
COLORS = {"USDC": "#2775CA", "USDT": "#26A17B", "DAI": "#F5AC37", "USDS": "#1AAB9B"}
PRESENT = [s for s in SYMBOLS if s in df["symbol"].values]

tab_rates, tab_rf, tab_liq = st.tabs(["📈 Rates", "🏦 Reserve Factor", "💧 Liquidity"])

# =====================================================================
# Tab 1: Rates
# =====================================================================
with tab_rates:
    st.subheader("Stablecoin Borrow APY vs BTC Price")
    fig = go.Figure()
    if not btc_df.empty:
        fig.add_trace(go.Scatter(
            x=btc_df["date"], y=btc_df["btc_price"], name="BTC Price", yaxis="y2",
            line=dict(color="rgba(247,147,26,0.35)", width=2),
            fill="tozeroy", fillcolor="rgba(247,147,26,0.06)",
            hovertemplate="BTC: $%{y:,.0f}<extra></extra>",
        ))
    for sym in PRESENT:
        g = df[df["symbol"] == sym].sort_values("date")
        fig.add_trace(go.Scatter(
            x=g["date"], y=g["borrow_apy"], name=f"{sym} Borrow",
            line=dict(color=COLORS[sym], width=2.5, dash="dot"),
            hovertemplate=f"{sym}: %{{y:.2f}}%<extra></extra>",
        ))
    fig.update_layout(
        height=520,
        yaxis=dict(title="Borrow APY %", gridcolor="rgba(0,0,0,0.06)", rangemode="tozero"),
        yaxis2=dict(title=dict(text="BTC Price (USD)", font=dict(color="#F7931A")),
                    tickfont=dict(color="#F7931A"), tickformat="$,.0f",
                    overlaying="y", side="right", showgrid=False),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M3", tickformat="%b %Y"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Average rate summary (USDC/USDT focus per spec — but show all available)
    average_rate_summary(df, "borrow_apy", symbols=PRESENT)

    st.divider()

    cols = st.columns(len(PRESENT) + 2)
    for i, sym in enumerate(PRESENT):
        g = df[df["symbol"] == sym].sort_values("date")
        cur = g.iloc[-1]["borrow_apy"]
        prev = g.iloc[-4]["borrow_apy"] if len(g) > 4 else cur
        cols[i].metric(f"{sym} Borrow", f"{cur:.2f}%", f"{cur-prev:+.2f}% vs 1mo")
    if not btc_df.empty:
        cols[len(PRESENT)].metric("BTC Price", f"${btc_df.iloc[-1]['btc_price']:,.0f}")
    cols[-1].metric("Avg (all symbols, 2Y)", f"{df['borrow_apy'].mean():.2f}%")

    st.divider()

    st.subheader("Pool Utilization (historical)")
    fig_util = go.Figure()
    for sym in PRESENT:
        g = df[df["symbol"] == sym].sort_values("date")
        fig_util.add_trace(go.Scatter(
            x=g["date"], y=g["utilization"], name=sym,
            line=dict(color=COLORS[sym], width=2),
            hovertemplate=f"{sym}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_util.update_layout(
        height=350,
        yaxis=dict(title="Utilization %", range=[0, 100], gridcolor="rgba(0,0,0,0.06)"),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M3", tickformat="%b %Y"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_util, use_container_width=True)

    # Correlation USDC
    usdc = df[df["symbol"] == "USDC"].sort_values("date")
    if not usdc.empty and not btc_df.empty:
        merged = pd.merge_asof(
            usdc[["date", "borrow_apy"]].sort_values("date"),
            btc_df.sort_values("date"),
            on="date", direction="nearest", tolerance=pd.Timedelta("7d"),
        )
        if "btc_price" in merged.columns and len(merged) > 10:
            corr = merged["borrow_apy"].corr(merged["btc_price"])
            st.markdown(f"**USDC Borrow APY vs BTC Price:** {corr:.2f}")

    with st.expander("Raw weekly data"):
        tab_names = PRESENT + ["BTC Price"]
        sub_tabs = st.tabs(tab_names)
        for i, sym in enumerate(PRESENT):
            with sub_tabs[i]:
                g = df[df["symbol"] == sym][["date", "borrow_apy", "supply_apy", "utilization"]].copy()
                g.columns = ["Date", "Borrow APY %", "Supply APY %", "Utilization %"]
                st.dataframe(g.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
        with sub_tabs[-1]:
            if not btc_df.empty:
                show = btc_df.copy()
                show.columns = ["Date", "BTC Price (USD)"]
                st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)


# =====================================================================
# Tab 2: Reserve Factor
# =====================================================================
with tab_rf:
    st.subheader("Reserve Factor — USDC & USDT (monthly)")
    reserve_factor_tab("Spark Lend", symbols=["USDC", "USDT"])


# =====================================================================
# Tab 3: Liquidity
# =====================================================================
with tab_liq:
    st.subheader("Current pool liquidity & BTC collateral")
    liquidity_tab("Spark Lend")

st.caption(
    "**Source:** Spark Lend Ethereum rates from [The Graph](https://thegraph.com) "
    "(Messari subgraph, marketDailySnapshot). BTC price from [DeFi Llama](https://coins.llama.fi)."
)

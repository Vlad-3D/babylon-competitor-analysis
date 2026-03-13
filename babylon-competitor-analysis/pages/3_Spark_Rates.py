"""Spark Lend — Stablecoin Borrow Rates (BTC Collateral) vs BTC Price.

Reads pre-collected data from data/spark_stable.csv and data/btc_price.csv.
Run collect_data.py first to populate these files.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="Spark Rates", page_icon="⚡", layout="wide")

from src.auth import check_password
check_password()

DATA_DIR = Path(__file__).parent.parent / "data"

st.title("Spark Lend — Stablecoin Borrow Rates")
st.caption(
    "Variable borrow APY for USDC, USDT, DAI & USDS on Spark Lend (Ethereum) — "
    "borrowing stablecoins against BTC collateral (WBTC, cbBTC, LBTC, tBTC). "
    "Weekly on-chain data via The Graph (Messari subgraph), last 2 years."
)


# --- Load data ---
@st.cache_data(ttl=300)
def load_spark() -> pd.DataFrame:
    path = DATA_DIR / "spark_stable.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    # Rename for consistency with other pages
    df = df.rename(columns={"borrow_rate": "borrow_apy", "supply_rate": "supply_apy"})
    return df


@st.cache_data(ttl=300)
def load_btc() -> pd.DataFrame:
    path = DATA_DIR / "btc_price.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["date"])


df = load_spark()
btc_df = load_btc()

if df.empty:
    st.error("No Spark rate data found. Run `uv run python collect_data.py` to collect data first.")
    st.stop()

SYMBOLS = ["USDC", "USDT", "DAI", "USDS"]
COLORS = {
    "USDC": "#2775CA",
    "USDT": "#26A17B",
    "DAI": "#F5AC37",
    "USDS": "#1AAB9B",
}

# =====================================================================
# Chart 1: Borrow Rates vs BTC Price
# =====================================================================
st.subheader("Stablecoin Borrow APY vs BTC Price")

fig = go.Figure()

if not btc_df.empty:
    fig.add_trace(go.Scatter(
        x=btc_df["date"], y=btc_df["btc_price"],
        name="BTC Price", yaxis="y2",
        line=dict(color="rgba(247, 147, 26, 0.35)", width=2),
        fill="tozeroy", fillcolor="rgba(247, 147, 26, 0.06)",
        hovertemplate="BTC: $%{y:,.0f}<extra></extra>",
    ))

for symbol in SYMBOLS:
    group = df[df["symbol"] == symbol].sort_values("date")
    if group.empty:
        continue
    fig.add_trace(go.Scatter(
        x=group["date"], y=group["borrow_apy"],
        name=f"{symbol} Borrow",
        line=dict(color=COLORS.get(symbol, "#888"), width=2.5, dash="dot"),
        hovertemplate=f"{symbol}: " + "%{y:.2f}%<extra></extra>",
    ))

fig.update_layout(
    height=520,
    yaxis=dict(
        title=dict(text="Borrow APY %", font=dict(color="#555")),
        tickfont=dict(color="#555"),
        gridcolor="rgba(0,0,0,0.06)", side="left", rangemode="tozero",
    ),
    yaxis2=dict(
        title=dict(text="BTC Price (USD)", font=dict(color="#F7931A")),
        tickfont=dict(color="#F7931A"), tickformat="$,.0f",
        overlaying="y", side="right", showgrid=False,
    ),
    xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M3", tickformat="%b %Y"),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02,
        xanchor="center", x=0.5, font=dict(size=13),
    ),
    margin=dict(l=10, r=10, t=10, b=10),
    hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
)

st.plotly_chart(fig, use_container_width=True)

# =====================================================================
# KPI Row
# =====================================================================
st.divider()

symbols_present = [s for s in SYMBOLS if s in df["symbol"].values]
cols = st.columns(len(symbols_present) + 2)

for i, sym in enumerate(symbols_present):
    group = df[df["symbol"] == sym].sort_values("date")
    current = group.iloc[-1]["borrow_apy"]
    prev = group.iloc[-4]["borrow_apy"] if len(group) > 4 else current
    with cols[i]:
        st.metric(f"{sym} Borrow", f"{current:.2f}%", delta=f"{current - prev:+.2f}% vs 1mo")

if not btc_df.empty:
    with cols[len(symbols_present)]:
        st.metric("BTC Price", f"${btc_df.iloc[-1]['btc_price']:,.0f}")

with cols[min(len(symbols_present) + 1, len(cols) - 1)]:
    st.metric("2Y Avg Borrow", f"{df['borrow_apy'].mean():.2f}%")

# =====================================================================
# Utilization
# =====================================================================
st.divider()
st.subheader("Pool Utilization")

fig_util = go.Figure()
for sym in SYMBOLS:
    group = df[df["symbol"] == sym].sort_values("date")
    if group.empty:
        continue
    fig_util.add_trace(go.Scatter(
        x=group["date"], y=group["utilization"],
        name=sym,
        line=dict(color=COLORS.get(sym, "#888"), width=2),
        hovertemplate=f"{sym}: " + "%{y:.1f}%<extra></extra>",
    ))

fig_util.update_layout(
    height=350,
    yaxis=dict(
        title=dict(text="Utilization %", font=dict(color="#555")),
        tickfont=dict(color="#555"),
        gridcolor="rgba(0,0,0,0.06)", range=[0, 100],
    ),
    xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M3", tickformat="%b %Y"),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02,
        xanchor="center", x=0.5, font=dict(size=13),
    ),
    margin=dict(l=10, r=10, t=10, b=10),
    hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
)

st.plotly_chart(fig_util, use_container_width=True)
st.caption("Utilization = Total Borrowed / Total Supplied. Higher utilization drives higher borrow rates.")

# =====================================================================
# Correlation
# =====================================================================
st.divider()
st.subheader("Rate-Price Correlation")

usdc_corr = df[df["symbol"] == "USDC"].sort_values("date")
if not usdc_corr.empty and not btc_df.empty:
    merged = pd.merge_asof(
        usdc_corr[["date", "borrow_apy"]].sort_values("date"),
        btc_df.sort_values("date"),
        on="date", direction="nearest", tolerance=pd.Timedelta("7d"),
    )
    if "btc_price" in merged.columns and len(merged) > 10:
        corr = merged["borrow_apy"].corr(merged["btc_price"])
        st.markdown(f"USDC Borrow APY vs BTC Price: **{corr:.2f}**")
        if abs(corr) > 0.3:
            st.info("Moderate correlation — borrowing demand rises with BTC price.")
        else:
            st.info("Weak correlation — Spark rates driven more by pool utilization than BTC price directly.")

# =====================================================================
# Raw data
# =====================================================================
st.divider()

with st.expander("Raw weekly data"):
    tab_names = [s for s in SYMBOLS if s in df["symbol"].values] + ["BTC Price"]
    tabs = st.tabs(tab_names)

    for i, sym in enumerate([s for s in SYMBOLS if s in df["symbol"].values]):
        with tabs[i]:
            group = df[df["symbol"] == sym][["date", "borrow_apy", "supply_apy", "utilization"]].copy()
            group.columns = ["Date", "Borrow APY %", "Supply APY %", "Utilization %"]
            st.dataframe(group.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

    with tabs[-1]:
        if not btc_df.empty:
            show = btc_df.copy()
            show.columns = ["Date", "BTC Price (USD)"]
            st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

st.caption(
    "**Data source:** Spark Lend Ethereum on-chain rates from [The Graph](https://thegraph.com) "
    "(Messari subgraph — marketDailySnapshot, USDC/USDT/DAI/USDS markets). "
    "BTC price from [DeFi Llama](https://coins.llama.fi). Weekly resampled (Friday)."
)

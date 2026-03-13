"""Aave V3 Interest Rates (USDC + USDT) vs BTC Price — last 2 years, weekly.

Reads pre-collected data from data/aave_rates.csv and data/btc_price.csv.
Run collect_data.py first to populate these files.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="Aave Rates vs BTC", page_icon="₿", layout="wide")

from src.auth import check_password
check_password()

DATA_DIR = Path(__file__).parent.parent / "data"

st.title("Aave V3 Interest Rates vs BTC Price")
st.caption("USDC & USDT borrow rates on Aave V3 Ethereum — weekly on-chain data via The Graph, last 2 years")


# --- Load data from files ---
@st.cache_data(ttl=300)
def load_rates() -> pd.DataFrame:
    path = DATA_DIR / "aave_rates.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["date"])


@st.cache_data(ttl=300)
def load_btc() -> pd.DataFrame:
    path = DATA_DIR / "btc_price.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["date"])


rates_df = load_rates()
btc_df = load_btc()

if rates_df.empty:
    st.error("No Aave rate data found. Run `uv run python collect_data.py` to collect data first.")
    st.stop()

usdc_df = rates_df[rates_df["symbol"] == "USDC"].copy()
usdt_df = rates_df[rates_df["symbol"] == "USDT"].copy()

# =====================================================================
# Chart: Borrow Rates vs BTC
# =====================================================================
st.subheader("Borrow Rates (Borrowers Pay)")

fig_borrow = go.Figure()

if not btc_df.empty:
    fig_borrow.add_trace(go.Scatter(
        x=btc_df["date"], y=btc_df["btc_price"],
        name="BTC Price", yaxis="y2",
        line=dict(color="rgba(247, 147, 26, 0.35)", width=2),
        fill="tozeroy", fillcolor="rgba(247, 147, 26, 0.06)",
        hovertemplate="BTC: $%{y:,.0f}<extra></extra>",
    ))

if not usdc_df.empty:
    fig_borrow.add_trace(go.Scatter(
        x=usdc_df["date"], y=usdc_df["borrow_apy"],
        name="USDC Borrow APY",
        line=dict(color="#2775CA", width=2.5, dash="dot"),
        hovertemplate="USDC Borrow: %{y:.2f}%<extra></extra>",
    ))

if not usdt_df.empty:
    fig_borrow.add_trace(go.Scatter(
        x=usdt_df["date"], y=usdt_df["borrow_apy"],
        name="USDT Borrow APY",
        line=dict(color="#26A17B", width=2.5, dash="dot"),
        hovertemplate="USDT Borrow: %{y:.2f}%<extra></extra>",
    ))

fig_borrow.update_layout(
    height=500,
    yaxis=dict(
        title=dict(text="Borrow APY %", font=dict(color="#555")),
        tickfont=dict(color="#555"),
        gridcolor="rgba(0,0,0,0.06)", side="left",
    ),
    yaxis2=dict(
        title=dict(text="BTC Price (USD)", font=dict(color="#F7931A")),
        tickfont=dict(color="#F7931A"), tickformat="$,.0f",
        overlaying="y", side="right", showgrid=False,
    ),
    xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M3", tickformat="%b %Y"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=13)),
    margin=dict(l=10, r=10, t=10, b=10),
    hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
)

st.plotly_chart(fig_borrow, use_container_width=True)

st.divider()

# --- KPI Row ---
col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    if not usdc_df.empty:
        current = usdc_df.iloc[-1]["supply_apy"]
        prev = usdc_df.iloc[-5]["supply_apy"] if len(usdc_df) > 5 else current
        st.metric("USDC Supply", f"{current:.2f}%", delta=f"{current - prev:+.2f}% vs 1mo")

with col2:
    if not usdc_df.empty:
        current = usdc_df.iloc[-1]["borrow_apy"]
        prev = usdc_df.iloc[-5]["borrow_apy"] if len(usdc_df) > 5 else current
        st.metric("USDC Borrow", f"{current:.2f}%", delta=f"{current - prev:+.2f}% vs 1mo")

with col3:
    if not usdt_df.empty:
        current = usdt_df.iloc[-1]["supply_apy"]
        prev = usdt_df.iloc[-5]["supply_apy"] if len(usdt_df) > 5 else current
        st.metric("USDT Supply", f"{current:.2f}%", delta=f"{current - prev:+.2f}% vs 1mo")

with col4:
    if not usdt_df.empty:
        current = usdt_df.iloc[-1]["borrow_apy"]
        prev = usdt_df.iloc[-5]["borrow_apy"] if len(usdt_df) > 5 else current
        st.metric("USDT Borrow", f"{current:.2f}%", delta=f"{current - prev:+.2f}% vs 1mo")

with col5:
    if not btc_df.empty:
        st.metric("BTC Price", f"${btc_df.iloc[-1]['btc_price']:,.0f}")

with col6:
    if not usdc_df.empty:
        st.metric("USDC 2Y Avg Borrow", f"{usdc_df['borrow_apy'].mean():.2f}%")

st.divider()

# --- Utilization chart ---
st.subheader("Pool Utilization")

if "utilization" in usdc_df.columns and usdc_df["utilization"].notna().any():
    fig_util = go.Figure()
    fig_util.add_trace(go.Scatter(
        x=usdc_df["date"], y=usdc_df["utilization"],
        name="USDC Utilization",
        line=dict(color="#2775CA", width=2),
        fill="tozeroy", fillcolor="rgba(39, 117, 202, 0.08)",
        hovertemplate="USDC: %{y:.1f}%<extra></extra>",
    ))

    if not usdt_df.empty and "utilization" in usdt_df.columns:
        fig_util.add_trace(go.Scatter(
            x=usdt_df["date"], y=usdt_df["utilization"],
            name="USDT Utilization",
            line=dict(color="#26A17B", width=2),
            hovertemplate="USDT: %{y:.1f}%<extra></extra>",
        ))

    fig_util.update_layout(
        height=350,
        yaxis=dict(
            title=dict(text="Utilization %", font=dict(color="#555")),
            tickfont=dict(color="#555"),
            gridcolor="rgba(0,0,0,0.06)", range=[0, 100],
        ),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M3", tickformat="%b %Y"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=13)),
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_util, use_container_width=True)
    st.caption("Utilization = Total Borrowed / Total Supplied. Higher utilization drives higher rates.")

st.divider()

# --- Correlation ---
st.subheader("Rate-Price Correlation")

if not usdc_df.empty and not btc_df.empty:
    merged = pd.merge_asof(
        usdc_df[["date", "supply_apy", "borrow_apy"]].sort_values("date"),
        btc_df.sort_values("date"),
        on="date", direction="nearest", tolerance=pd.Timedelta("7d"),
    )
    if "btc_price" in merged.columns and len(merged) > 10:
        corr_supply = merged["supply_apy"].corr(merged["btc_price"])
        corr_borrow = merged["borrow_apy"].corr(merged["btc_price"])
        st.markdown(
            f"USDC Supply APY vs BTC: **{corr_supply:.2f}** | "
            f"USDC Borrow APY vs BTC: **{corr_borrow:.2f}**"
        )
        if abs(corr_borrow) > 0.3:
            st.info("Moderate correlation — borrowing demand rises with BTC price as traders leverage up.")
        else:
            st.info("Weak correlation — stablecoin rates driven more by DeFi utilization than BTC price directly.")

st.divider()

# --- Data table ---
with st.expander("Raw weekly data"):
    tabs = st.tabs(["USDC", "USDT", "BTC"])
    with tabs[0]:
        if not usdc_df.empty:
            show = usdc_df[["date", "supply_apy", "borrow_apy", "utilization"]].copy()
            show.columns = ["Date", "Supply APY %", "Borrow APY %", "Utilization %"]
            st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
    with tabs[1]:
        if not usdt_df.empty:
            show = usdt_df[["date", "supply_apy", "borrow_apy", "utilization"]].copy()
            show.columns = ["Date", "Supply APY %", "Borrow APY %", "Utilization %"]
            st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
    with tabs[2]:
        if not btc_df.empty:
            show = btc_df.copy()
            show.columns = ["Date", "BTC Price (USD)"]
            st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

st.caption(
    "**Data sources:** Aave V3 Ethereum on-chain rates from [The Graph](https://thegraph.com) "
    "(ReserveParamsHistoryItem — liquidityRate & variableBorrowRate in RAY). "
    "BTC price from [DeFi Llama](https://coins.llama.fi). Weekly resampled (Friday)."
)

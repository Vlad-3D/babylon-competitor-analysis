"""Morpho Blue — USDC/USDT borrow rates against BTC collateral."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="Morpho Blue", page_icon="🦋", layout="wide")

from src.auth import check_password
check_password()

from src.ui_helpers import average_rate_summary, reserve_factor_tab, liquidity_tab

DATA_DIR = Path(__file__).parent.parent / "data"

st.title("Morpho Blue — USDC & USDT against BTC")
st.caption("Borrow stablecoins on isolated markets with wBTC / cbBTC as collateral.")


@st.cache_data(ttl=300)
def load_morpho() -> pd.DataFrame:
    p = DATA_DIR / "morpho_btc_borrow.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


@st.cache_data(ttl=300)
def load_btc() -> pd.DataFrame:
    p = DATA_DIR / "btc_price.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


df = load_morpho()
btc_df = load_btc()

if df.empty:
    st.error("No Morpho rate data found. Run `uv run python collect_data.py`.")
    st.stop()

usdc_df = df[df["symbol"] == "USDC"].sort_values("date")
usdt_df = df[df["symbol"] == "USDT"].sort_values("date")

COLORS = {"USDC": "#2775CA", "USDT": "#26A17B"}

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
    if not usdc_df.empty:
        fig.add_trace(go.Scatter(
            x=usdc_df["date"], y=usdc_df["borrow_apy"], name="USDC Borrow APY",
            line=dict(color=COLORS["USDC"], width=2.5, dash="dot"),
            hovertemplate="USDC Borrow: %{y:.2f}%<extra></extra>",
        ))
    if not usdt_df.empty:
        fig.add_trace(go.Scatter(
            x=usdt_df["date"], y=usdt_df["borrow_apy"], name="USDT Borrow APY",
            line=dict(color=COLORS["USDT"], width=2.5, dash="dot"),
            hovertemplate="USDT Borrow: %{y:.2f}%<extra></extra>",
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

    average_rate_summary(df, "borrow_apy", symbols=["USDC", "USDT"])

    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    if not usdc_df.empty:
        cur = usdc_df.iloc[-1]["borrow_apy"]
        prev = usdc_df.iloc[-4]["borrow_apy"] if len(usdc_df) > 4 else cur
        col1.metric("USDC Borrow", f"{cur:.2f}%", f"{cur-prev:+.2f}% vs 1mo")
    if not usdt_df.empty:
        cur = usdt_df.iloc[-1]["borrow_apy"]
        prev = usdt_df.iloc[-4]["borrow_apy"] if len(usdt_df) > 4 else cur
        col2.metric("USDT Borrow", f"{cur:.2f}%", f"{cur-prev:+.2f}% vs 1mo")
    if not btc_df.empty:
        col3.metric("BTC Price", f"${btc_df.iloc[-1]['btc_price']:,.0f}")
    col4.metric("2Y Avg Borrow", f"{df['borrow_apy'].mean():.2f}%")

    st.divider()

    st.subheader("Pool Utilization (historical)")
    if "utilization" in df.columns and df["utilization"].notna().any():
        fig_util = go.Figure()
        if not usdc_df.empty:
            fig_util.add_trace(go.Scatter(
                x=usdc_df["date"], y=usdc_df["utilization"], name="USDC",
                line=dict(color=COLORS["USDC"], width=2),
                fill="tozeroy", fillcolor="rgba(39,117,202,0.08)",
                hovertemplate="USDC: %{y:.1f}%<extra></extra>",
            ))
        if not usdt_df.empty:
            fig_util.add_trace(go.Scatter(
                x=usdt_df["date"], y=usdt_df["utilization"], name="USDT",
                line=dict(color=COLORS["USDT"], width=2),
                hovertemplate="USDT: %{y:.1f}%<extra></extra>",
            ))
        fig_util.update_layout(
            height=320,
            yaxis=dict(title="Utilization %", range=[0, 100], gridcolor="rgba(0,0,0,0.06)"),
            xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M3", tickformat="%b %Y"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            margin=dict(l=10, r=10, t=10, b=10),
            hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_util, use_container_width=True)

    if not usdc_df.empty and not btc_df.empty:
        merged = pd.merge_asof(
            usdc_df[["date", "borrow_apy"]].sort_values("date"),
            btc_df.sort_values("date"),
            on="date", direction="nearest", tolerance=pd.Timedelta("7d"),
        )
        if "btc_price" in merged.columns and len(merged) > 10:
            corr = merged["borrow_apy"].corr(merged["btc_price"])
            st.markdown(f"**USDC Borrow APY vs BTC Price:** {corr:.2f}")

    with st.expander("Raw weekly data"):
        sub_tabs = st.tabs(["USDC", "USDT", "BTC"])
        with sub_tabs[0]:
            if not usdc_df.empty:
                show = usdc_df[["date", "borrow_apy", "utilization"]].copy()
                show.columns = ["Date", "Borrow APY %", "Utilization %"]
                st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
        with sub_tabs[1]:
            if not usdt_df.empty:
                show = usdt_df[["date", "borrow_apy", "utilization"]].copy()
                show.columns = ["Date", "Borrow APY %", "Utilization %"]
                st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
        with sub_tabs[2]:
            if not btc_df.empty:
                show = btc_df.copy()
                show.columns = ["Date", "BTC Price (USD)"]
                st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)


# =====================================================================
# Tab 2: Reserve Factor
# =====================================================================
with tab_rf:
    st.subheader("Reserve Factor — USDC & USDT (monthly)")
    reserve_factor_tab("Morpho Blue", symbols=["USDC", "USDT"])


# =====================================================================
# Tab 3: Liquidity
# =====================================================================
with tab_liq:
    st.subheader("Current per-market liquidity & BTC collateral")
    liquidity_tab("Morpho Blue")

st.caption(
    "**Source:** Morpho Blue on-chain rates from [The Graph](https://thegraph.com) "
    "(MarketDailySnapshot, borrow-weighted across BTC-collateral markets). BTC price from [DeFi Llama](https://coins.llama.fi)."
)

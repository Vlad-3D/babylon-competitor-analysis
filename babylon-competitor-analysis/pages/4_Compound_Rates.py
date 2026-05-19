"""Compound V3 — USDC/USDT borrow rates against BTC collateral."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="Compound V3", page_icon="🟢", layout="wide")

from src.auth import check_password
check_password()

from src.ui_helpers import average_rate_summary, reserve_factor_tab, liquidity_tab

DATA_DIR = Path(__file__).parent.parent / "data"

st.title("Compound V3 — USDC & USDT against BTC")
st.caption("Borrow rates for USDC & USDT Comet markets — wBTC, cbBTC, LBTC, tBTC accepted as collateral.")


@st.cache_data(ttl=300)
def load_compound() -> pd.DataFrame:
    p = DATA_DIR / "compound_btc_borrow.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


@st.cache_data(ttl=300)
def load_btc() -> pd.DataFrame:
    p = DATA_DIR / "btc_price.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


df = load_compound()
btc_df = load_btc()

# Filter to last 2 years for charts (Compound USDC has ~4y, USDT has ~1y of data)
_two_years_ago = pd.Timestamp.now() - pd.DateOffset(years=2)
if not df.empty:
    df = df[df["date"] >= _two_years_ago]
if not btc_df.empty:
    btc_df = btc_df[btc_df["date"] >= _two_years_ago]

if df.empty:
    st.error("No Compound rate data found. Run `uv run python collect_data.py`.")
    st.stop()

SYMBOLS = ["USDC", "USDT"]
COLORS = {"USDC": "#2775CA", "USDT": "#26A17B"}
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
    cols[-1].metric("Avg Borrow", f"{df['borrow_apy'].mean():.2f}%")

    st.divider()

    st.subheader("Pool Utilization (historical)")
    if "utilization" in df.columns and df["utilization"].notna().any():
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

    usdc_corr = df[df["symbol"] == "USDC"].sort_values("date")
    if not usdc_corr.empty and not btc_df.empty:
        merged = pd.merge_asof(
            usdc_corr[["date", "borrow_apy"]].sort_values("date"),
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
                g = df[df["symbol"] == sym][["date", "borrow_apy", "utilization"]].copy()
                g.columns = ["Date", "Borrow APY %", "Utilization %"]
                st.dataframe(g.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
        with sub_tabs[-1]:
            if not btc_df.empty:
                show = btc_df.copy()
                show.columns = ["Date", "BTC Price (USD)"]
                st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)


# =====================================================================
# Tab 2: Reserve Factor (implicit — no explicit parameter in Comet)
# =====================================================================
with tab_rf:
    st.subheader("Implicit Reserve Factor (derived from rate spread)")
    st.caption(
        "Compound V3 has **no explicit reserveFactor parameter**. Unlike Aave V3, the protocol "
        "uses two independent rate curves and earns the spread between them. We compute the "
        "*implicit* RF each week as `1 − supplyApr / (borrowApr × utilization)` — the share of "
        "borrower interest the protocol keeps. Unlike Aave's fixed 10%, this varies with utilization."
    )
    reserve_factor_tab("Compound V3")


# =====================================================================
# Tab 3: Liquidity
# =====================================================================
with tab_liq:
    st.subheader("Current pool liquidity & BTC collateral")
    liquidity_tab("Compound V3")

st.caption(
    "**Source:** Compound V3 (Comet) rates from [The Graph](https://thegraph.com) "
    "(Paperclip Labs subgraph). BTC price from [DeFi Llama](https://coins.llama.fi)."
)

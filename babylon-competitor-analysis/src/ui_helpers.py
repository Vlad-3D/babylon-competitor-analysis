"""Shared UI helpers for rate/RF/liquidity sections across lending pages."""

from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

DATA_DIR = Path(__file__).parent.parent / "data"

# Brand colors
COLOR_USDC = "#2775CA"
COLOR_USDT = "#26A17B"


@st.cache_data(ttl=300)
def load_reserve_factor() -> pd.DataFrame:
    p = DATA_DIR / "reserve_factor.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, parse_dates=["date"])


@st.cache_data(ttl=300)
def load_liquidity_stable() -> pd.DataFrame:
    p = DATA_DIR / "liquidity_stablecoin.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


@st.cache_data(ttl=300)
def load_liquidity_btc() -> pd.DataFrame:
    p = DATA_DIR / "liquidity_btc_collateral.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def average_rate_summary(rates_df: pd.DataFrame, rate_col: str, symbols: list[str] | None = None,
                          rate_is_decimal: bool = False, label: str = "Average Borrow APY"):
    """Render a compact average-rate summary (1Y, 2Y, All-time) per symbol.

    Args:
      rates_df: DataFrame with columns [date, symbol, <rate_col>]
      rate_col: column containing the borrow rate
      symbols: list of symbols to include (default: all unique)
      rate_is_decimal: True if rate is stored as 0.05 (=5%), False if 5.0
      label: section label
    """
    if rates_df.empty or rate_col not in rates_df.columns:
        return

    if symbols is None:
        symbols = sorted(rates_df["symbol"].unique().tolist())

    rates_df = rates_df.copy()
    rates_df["date"] = pd.to_datetime(rates_df["date"])
    factor = 100.0 if rate_is_decimal else 1.0

    now = rates_df["date"].max()
    cutoff_1y = now - pd.Timedelta(days=365)
    cutoff_2y = now - pd.Timedelta(days=730)

    st.markdown(f"**{label} — averages**")
    cols = st.columns(len(symbols))
    for i, sym in enumerate(symbols):
        sub = rates_df[rates_df["symbol"] == sym]
        if sub.empty:
            continue
        avg_1y = sub[sub["date"] >= cutoff_1y][rate_col].mean() * factor
        avg_2y = sub[sub["date"] >= cutoff_2y][rate_col].mean() * factor
        avg_all = sub[rate_col].mean() * factor
        with cols[i]:
            st.markdown(
                f"<div style='padding:8px;border-left:3px solid {('#2775CA' if 'USDC' in sym else '#26A17B' if 'USDT' in sym else '#888')};"
                f"background:rgba(127,127,127,0.04);border-radius:4px;'>"
                f"<div style='font-size:13px;font-weight:600;margin-bottom:4px'>{sym}</div>"
                f"<div style='font-size:12px;color:#666'>1Y avg: <b>{avg_1y:.2f}%</b></div>"
                f"<div style='font-size:12px;color:#666'>2Y avg: <b>{avg_2y:.2f}%</b></div>"
                f"<div style='font-size:12px;color:#666'>All-time: <b>{avg_all:.2f}%</b></div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def reserve_factor_tab(protocol: str, symbols: list[str] = ("USDC", "USDT")):
    """Render a Reserve Factor history chart + current values for the given protocol."""
    df = load_reserve_factor()
    if df.empty:
        st.warning("Reserve factor data not available — run `collect_data.py`.")
        return

    sub = df[(df["protocol"] == protocol) & (df["symbol"].isin(symbols))]
    if sub.empty:
        st.info(f"No reserve factor history for {protocol} {symbols}.")
        return

    fig = go.Figure()
    for sym in symbols:
        s = sub[sub["symbol"] == sym].sort_values("date")
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s["date"], y=s["reserve_factor"],
            name=f"{sym} Reserve Factor",
            mode="lines+markers",
            line=dict(width=2.5, color=COLOR_USDC if sym == "USDC" else COLOR_USDT),
            hovertemplate=f"{sym}: %{{y:.2f}}%<extra></extra>",
        ))
    fig.update_layout(
        height=380,
        yaxis=dict(title="Reserve Factor %", gridcolor="rgba(0,0,0,0.06)", rangemode="tozero"),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M6", tickformat="%b %Y"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Current value KPIs
    cols = st.columns(len(symbols))
    for i, sym in enumerate(symbols):
        s = sub[sub["symbol"] == sym].sort_values("date")
        if s.empty:
            continue
        latest = s.iloc[-1]["reserve_factor"]
        with cols[i]:
            st.metric(f"{sym} Current RF", f"{latest:.2f}%")

    notes = {
        "Aave V3": "**Source:** real `ReserveFactorChanged` events from PoolConfigurator (Etherscan). RF has not changed since market launch — single event captured.",
        "Spark Lend": "**Source:** current value from Messari subgraph. Spark routes parameter changes through Maker spells (not standard PoolConfigurator events), so on-chain history isn't directly queryable — only the current setting is shown.",
        "Morpho Blue": "**Source:** real `SetFee` / `CreateMarket` events from Morpho Blue (Etherscan). Markets begin with 0% fee at creation and most BTC-collateral markets have never had it changed.",
        "Compound V3": "**Source:** implicit RF computed from real weekly rate snapshots — `1 − supplyApr / (borrowApr × utilization)`. Compound V3 has no explicit reserveFactor parameter; this is the share of borrower interest retained by the protocol on each snapshot.",
    }
    st.caption(notes.get(protocol, "Reserve Factor = share of borrower interest kept by the protocol."))


def liquidity_tab(protocol: str):
    """Render current Liquidity snapshot for the given protocol: USDC/USDT pools + BTC collateral."""
    stable = load_liquidity_stable()
    btc = load_liquidity_btc()
    if stable.empty and btc.empty:
        st.warning("Liquidity snapshot data not available — run `collect_data.py`.")
        return

    st.markdown("**Stablecoin pool liquidity (USDC / USDT)**")
    st_filt = stable[stable["protocol"] == protocol].copy() if not stable.empty else pd.DataFrame()
    if not st_filt.empty:
        show = st_filt[["market_label", "symbol", "supply_usd", "borrow_usd", "available_usd", "utilization"]].copy()
        show.columns = ["Market", "Asset", "Supplied $", "Borrowed $", "Available $", "Utilization %"]
        st.dataframe(
            show.style.format({
                "Supplied $": "${:,.0f}",
                "Borrowed $": "${:,.0f}",
                "Available $": "${:,.0f}",
                "Utilization %": "{:.1f}%",
            }),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info(f"No stablecoin pool data for {protocol}.")

    st.markdown("**BTC collateral in this protocol**")
    btc_filt = btc[btc["protocol"] == protocol].copy() if not btc.empty else pd.DataFrame()
    if not btc_filt.empty:
        show = btc_filt[["btc_symbol", "supplied_btc", "supplied_usd"]].copy()
        show.columns = ["BTC type", "BTC amount", "USD value"]
        show = show.sort_values("USD value", ascending=False)
        st.dataframe(
            show.style.format({
                "BTC amount": "{:,.2f}",
                "USD value": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )
        total_usd = btc_filt["supplied_usd"].sum()
        total_btc = btc_filt["supplied_btc"].sum()
        st.caption(f"Total BTC in pool: **{total_btc:,.0f} BTC** ≈ **${total_usd:,.0f}**")
    else:
        st.info(f"No BTC collateral data for {protocol}.")

"""Summary — all key charts on one page."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from src.config import CLUSTER_NAMES, CLUSTER_COLORS
from src.static_metadata import TRUST_SCORES, COMPETITOR_METADATA
from src.aggregate import aggregate_all

st.set_page_config(page_title="Babylon TBV — Competitor Intelligence", page_icon="₿", layout="wide")

from src.auth import check_password
check_password()

@st.cache_data(show_spinner="Loading data...", ttl=300)
def load_data():
    return aggregate_all()

df, warnings = load_data()

# Focus on 4 key competitors only
FOCUS_COMPETITORS = ["wBTC", "cbBTC", "LBTC", "tBTC"]
df = df[df["name"].isin(FOCUS_COMPETITORS + ["Babylon TBV"])].copy()

st.title("Summary")
st.caption("All key charts in one view")

for w in warnings:
    st.warning(w)

# --- KPI Row ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Competitors Tracked", len(df[df["name"] != "Babylon TBV"]))

with col2:
    total_tvl = pd.to_numeric(df["effective_tvl"], errors="coerce").sum()
    if total_tvl >= 1e9:
        st.metric("Combined TVL", f"${total_tvl / 1e9:.1f}B")
    else:
        st.metric("Combined TVL", f"${total_tvl / 1e6:.0f}M")

with col3:
    st.metric("Babylon Staked", "$5B+")

with col4:
    holders_total = pd.to_numeric(df["holders_count"], errors="coerce").sum()
    if holders_total > 0:
        st.metric("Total Holders", f"{holders_total:,.0f}")
    else:
        st.metric("Total Holders", "Dune API required")

st.divider()

# Precompute common columns
df["effective_tvl_num"] = pd.to_numeric(df["effective_tvl"], errors="coerce").fillna(0)
df["trust_score"] = df["custody_type"].map(TRUST_SCORES).fillna(1)
df["integrations"] = pd.to_numeric(
    df.get("defi_integrations_count", pd.Series(dtype=float)), errors="coerce"
).fillna(0)
df["cluster_label"] = df["cluster"].map(CLUSTER_NAMES).fillna("Unknown")

# =====================================================================
# 1. TVL / AUM  +  TVL Growth in BTC (side by side)
# =====================================================================
import json as _json
from pathlib import Path as _Path

_col_left, _col_right = st.columns(2)

# --- LEFT: TVL / AUM bar chart ---
with _col_left:
    st.subheader("TVL / AUM by Cluster")

    chart_df = df[df["effective_tvl_num"] > 0].copy()

    if not chart_df.empty:
        chart_df = chart_df.sort_values("effective_tvl_num", ascending=False)
        ordered_names = chart_df["name"].tolist()

        chart_df["tvl_label"] = chart_df["effective_tvl_num"].apply(
            lambda x: f"${x / 1e9:.1f}B" if x >= 1e9 else f"${x / 1e6:.0f}M"
        )

        color_map = {v: CLUSTER_COLORS.get(k, "#888") for k, v in CLUSTER_NAMES.items()}

        fig_tvl = px.bar(
            chart_df,
            x="effective_tvl_num",
            y="name",
            color="cluster_label",
            orientation="h",
            text="tvl_label",
            color_discrete_map=color_map,
            category_orders={
                "cluster_label": [CLUSTER_NAMES[k] for k in sorted(CLUSTER_NAMES)],
                "name": ordered_names,
            },
        )
        fig_tvl.update_traces(textposition="outside", textfont_size=12)
        fig_tvl.update_layout(
            height=450,
            xaxis_title="TVL / AUM (USD)",
            yaxis_title="",
            legend_title="",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=11)),
            margin=dict(l=10, r=40, t=10, b=10),
        )
        st.plotly_chart(fig_tvl, use_container_width=True)

    st.caption(
        "🟠 DeFi Llama (on-chain TVL) · 🦎 CoinGecko (market cap) · 🟣 Research (manual AUM)"
    )

# --- RIGHT: TVL Growth in BTC ---
with _col_right:
    st.subheader("TVL Growth in BTC (2 Years)")

    _data_dir = _Path(__file__).parent / "data"
    _btc_prices_path = _data_dir / "btc_prices.json"
    _defillama_path = _data_dir / "defillama.json"

    if _btc_prices_path.exists() and _defillama_path.exists():
        with open(_btc_prices_path) as _f:
            _btc_prices = {int(k): v for k, v in _json.load(_f).items()}
        with open(_defillama_path) as _f:
            _dl_data = _json.load(_f)

        _slug_to_name = {}
        for _, _row in df[df["name"].isin(FOCUS_COMPETITORS)].iterrows():
            if pd.notna(_row.get("defillama_slug")):
                _slug_to_name[_row["defillama_slug"]] = _row["name"]

        def _find_btc_price(day_ts):
            p = _btc_prices.get(day_ts)
            if p and p > 0:
                return p
            for _offset in [86400, -86400, 2*86400, -2*86400]:
                p = _btc_prices.get(day_ts + _offset)
                if p and p > 0:
                    return p
            return None

        _growth_rows = []

        for _proto in _dl_data:
            _slug = _proto.get("defillama_slug", "")
            if _slug not in _slug_to_name:
                continue
            _name = _slug_to_name[_slug]
            for _ts, _tvl_usd in _proto.get("tvl_history", []):
                _day_ts = _ts - (_ts % 86400)
                _btc_price = _find_btc_price(_day_ts)
                if _btc_price:
                    _growth_rows.append({
                        "name": _name,
                        "date": pd.Timestamp(_day_ts, unit="s"),
                        "tvl_btc": _tvl_usd / _btc_price,
                    })

        _cbbtc_path = _data_dir / "cbbtc_tvl_history.json"
        if _cbbtc_path.exists():
            with open(_cbbtc_path) as _f:
                _cbbtc_hist = _json.load(_f)
            for _entry in _cbbtc_hist:
                _growth_rows.append({
                    "name": "cbBTC",
                    "date": pd.Timestamp(_entry["timestamp"], unit="s"),
                    "tvl_btc": _entry["tvl_btc"],
                })

        if _growth_rows:
            _growth_df = pd.DataFrame(_growth_rows)
            _growth_weekly = (
                _growth_df.set_index("date")
                .groupby("name")["tvl_btc"]
                .resample("W")
                .mean()
                .reset_index()
            )

            _color_map = {
                "wBTC": "#45B7D1",
                "cbBTC": "#DDA0DD",
                "LBTC": "#4ECDC4",
                "tBTC": "#FF6B6B",
            }

            # Stacked area — cumulative, shows market share shifts
            # Pivot to wide, fill gaps, then stack
            _pivot = _growth_weekly.pivot(index="date", columns="name", values="tvl_btc").sort_index()
            _pivot = _pivot.ffill().fillna(0)

            # Order: largest on bottom for visual stability
            _order = _pivot.iloc[-1].sort_values(ascending=False).index.tolist()
            _pivot = _pivot[_order]

            _fig_growth = go.Figure()
            for _name in reversed(_order):  # reversed so largest renders first (bottom)
                _fig_growth.add_trace(go.Scatter(
                    x=_pivot.index,
                    y=_pivot[_name],
                    name=_name,
                    mode="lines",
                    line=dict(width=0.5, color=_color_map.get(_name, "#888")),
                    fillcolor=_color_map.get(_name, "#888"),
                    stackgroup="one",
                    hovertemplate=f"<b>{_name}</b><br>%{{x|%b %Y}}<br>%{{y:,.0f}} BTC<extra></extra>",
                ))

            _fig_growth.update_layout(
                height=450,
                xaxis_title="",
                yaxis_title="Cumulative TVL (BTC)",
                legend_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=11)),
                margin=dict(l=10, r=10, t=10, b=10),
                yaxis=dict(tickformat=",.0f"),
                hovermode="x unified",
            )
            st.plotly_chart(_fig_growth, use_container_width=True)
        else:
            st.info("No historical TVL data available.")

    st.caption("Weekly average. TVL converted via daily BTC price. Source: DeFi Llama.")

st.divider()

# =====================================================================
# 2. Max LTV by BTC Token (Aave · Morpho · Spark)
# =====================================================================
st.header("2. Max LTV — How Much Can You Borrow?")
st.caption(
    "Current maximum Loan-to-Value across three major lending protocols. "
    "Higher LTV = more capital-efficient borrowing against your BTC."
)

_ltv_path = _Path(__file__).parent / "data" / "ltv_comparison.json"

if _ltv_path.exists():
    with open(_ltv_path) as _f:
        _ltv_raw = _json.load(_f)

    if _ltv_raw:
        _ltv_df = pd.DataFrame(_ltv_raw)

        # Filter to the 4 focus tokens only
        _ltv_df = _ltv_df[_ltv_df["token"].isin(FOCUS_COMPETITORS)].copy()

        # For Morpho: take the best (highest LTV) market per token
        _morpho = _ltv_df[_ltv_df["protocol"] == "Morpho Blue"]
        if not _morpho.empty:
            _morpho_best = _morpho.sort_values("max_ltv", ascending=False).drop_duplicates("token", keep="first")
            _ltv_df = pd.concat([
                _ltv_df[_ltv_df["protocol"] != "Morpho Blue"],
                _morpho_best,
            ], ignore_index=True)

        # Only show entries with LTV > 0
        _ltv_df = _ltv_df[_ltv_df["max_ltv"] > 0].copy()

        # --- Grouped bar chart: LTV by token, colored by protocol ---
        _protocol_colors = {
            "Aave V3": "#B6509E",
            "Morpho Blue": "#2775CA",
            "Spark Lend": "#F5AC37",
            "Compound V3": "#00D395",
            "Fluid": "#6C5CE7",
        }

        # Create a label like "wBTC" for the y-axis, protocol for color
        _token_order = ["wBTC", "cbBTC", "LBTC", "tBTC"]
        _ltv_df["token"] = pd.Categorical(_ltv_df["token"], categories=_token_order, ordered=True)
        _ltv_df = _ltv_df.sort_values(["token", "protocol"])

        _fig_ltv = go.Figure()

        for _proto in ["Aave V3", "Morpho Blue", "Spark Lend", "Compound V3", "Fluid"]:
            _proto_df = _ltv_df[_ltv_df["protocol"] == _proto]
            if _proto_df.empty:
                continue
            _fig_ltv.add_trace(go.Bar(
                y=_proto_df["token"].astype(str),
                x=_proto_df["max_ltv"],
                name=_proto,
                orientation="h",
                marker_color=_protocol_colors.get(_proto, "#888"),
                text=_proto_df["max_ltv"].apply(lambda v: f"{v:.0f}%"),
                textposition="outside",
                textfont_size=13,
                hovertemplate=(
                    "<b>%{y}</b> on " + _proto +
                    "<br>Max LTV: %{x:.0f}%<extra></extra>"
                ),
            ))

        _fig_ltv.update_layout(
            barmode="group",
            height=450,
            xaxis_title="Max LTV %",
            yaxis_title="",
            xaxis=dict(range=[0, 100], dtick=10, gridcolor="rgba(0,0,0,0.06)"),
            yaxis=dict(
                categoryorder="array",
                categoryarray=list(reversed(_token_order)),
                tickfont=dict(size=14),
            ),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="center", x=0.5, font=dict(size=13),
            ),
            margin=dict(l=10, r=40, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(_fig_ltv, use_container_width=True)

        st.divider()

        # --- Full comparison table ---
        st.subheader("Full Protocol Comparison")

        _table_rows = []
        for _tok in _token_order:
            _row = {"Token": _tok}
            for _proto in ["Aave V3", "Morpho Blue", "Spark Lend", "Compound V3", "Fluid"]:
                _match = _ltv_df[(_ltv_df["token"] == _tok) & (_ltv_df["protocol"] == _proto)]
                if not _match.empty:
                    _r = _match.iloc[0]
                    _ltv_val = _r["max_ltv"]
                    _liq_val = _r["liq_threshold"]
                    _borrow = _r.get("borrowing_enabled", True)
                    if _ltv_val > 0:
                        _cell = f"{_ltv_val:.0f}%"
                        if _liq_val > _ltv_val:
                            _cell += f" (liq {_liq_val:.0f}%)"
                        if not _borrow:
                            _cell += " *"
                    else:
                        _cell = "—"
                else:
                    _cell = "—"
                _row[_proto] = _cell
            _table_rows.append(_row)

        _table_df = pd.DataFrame(_table_rows)
        st.dataframe(_table_df, use_container_width=True, hide_index=True)

        st.caption(
            "**Max LTV** = maximum loan you can take as % of collateral value. "
            "**Liq** = liquidation threshold (you get liquidated above this). "
            "\\* = borrowing disabled (collateral-only mode). "
            "Morpho Blue LLTV = liquidation threshold (no separate initial LTV). "
            "Source: Aave V3 subgraph, Morpho Blue subgraph, Spark PoolDataProvider, "
            "Compound V3 subgraph, Fluid vault storage (Etherscan)."
        )
    else:
        st.info("No LTV comparison data. Run `collect_data.py` to fetch.")
else:
    st.info("No LTV comparison data file found. Run `uv run python collect_data.py` to collect.")

st.divider()

# =====================================================================
# 3. Borrow Rates — What Does It Cost?
# =====================================================================
st.header("3. Borrow Rates — What Does It Cost?")
st.caption(
    "USDC & USDT variable borrow APY across Aave V3, Morpho Blue, Spark Lend, and Compound V3 (Ethereum). "
    "Weekly on-chain data via The Graph, last 2 years. BTC price overlay shows market context."
)

_rates_data_dir = _Path(__file__).parent / "data"

@st.cache_data(ttl=300)
def _load_btc_price():
    _p = _rates_data_dir / "btc_price.csv"
    if not _p.exists():
        return pd.DataFrame()
    return pd.read_csv(_p, parse_dates=["date"])

_btc_price_df = _load_btc_price()

def _make_borrow_chart(rate_df, title, symbols=None, colors=None):
    """Build a compact borrow-rate chart with BTC price overlay."""
    if colors is None:
        colors = {"USDC": "#2775CA", "USDT": "#26A17B", "DAI": "#F5AC37", "USDS": "#1AAB9B"}
    if symbols is None:
        symbols = ["USDC", "USDT"]

    fig = go.Figure()

    if not _btc_price_df.empty:
        fig.add_trace(go.Scatter(
            x=_btc_price_df["date"], y=_btc_price_df["btc_price"],
            name="BTC", yaxis="y2",
            line=dict(color="rgba(247, 147, 26, 0.3)", width=1.5),
            fill="tozeroy", fillcolor="rgba(247, 147, 26, 0.05)",
            hovertemplate="BTC: $%{y:,.0f}<extra></extra>",
            showlegend=False,
        ))

    for sym in symbols:
        group = rate_df[rate_df["symbol"] == sym].sort_values("date")
        if group.empty:
            continue
        fig.add_trace(go.Scatter(
            x=group["date"], y=group["borrow_apy"],
            name=sym,
            line=dict(color=colors.get(sym, "#888"), width=2, dash="dot"),
            hovertemplate=f"{sym}: " + "%{y:.2f}%<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=350,
        yaxis=dict(
            title=dict(text="Borrow APY %", font=dict(size=11, color="#555")),
            tickfont=dict(size=10, color="#555"),
            gridcolor="rgba(0,0,0,0.06)", side="left", rangemode="tozero",
        ),
        yaxis2=dict(
            tickfont=dict(color="#F7931A", size=9), tickformat="$,.0f",
            overlaying="y", side="right", showgrid=False,
        ),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", dtick="M6", tickformat="%b %Y", tickfont=dict(size=10)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=11)),
        margin=dict(l=5, r=5, t=30, b=5),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig

# --- Row 1: Aave + Morpho ---
_rc1, _rc2 = st.columns(2)

with _rc1:
    _aave_path = _rates_data_dir / "aave_rates.csv"
    if _aave_path.exists():
        _aave_rates = pd.read_csv(_aave_path, parse_dates=["date"])
        st.plotly_chart(_make_borrow_chart(_aave_rates, "Aave V3"), use_container_width=True)
        _aave_usdc = _aave_rates[_aave_rates["symbol"] == "USDC"]
        if not _aave_usdc.empty:
            st.metric("USDC Borrow Now", f"{_aave_usdc.iloc[-1]['borrow_apy']:.2f}%")
    else:
        st.info("No Aave data. Run collect_data.py.")

with _rc2:
    _morpho_path = _rates_data_dir / "morpho_btc_borrow.csv"
    if _morpho_path.exists():
        _morpho_rates = pd.read_csv(_morpho_path, parse_dates=["date"])
        st.plotly_chart(_make_borrow_chart(_morpho_rates, "Morpho Blue"), use_container_width=True)
        _morpho_usdc = _morpho_rates[_morpho_rates["symbol"] == "USDC"]
        if not _morpho_usdc.empty:
            st.metric("USDC Borrow Now", f"{_morpho_usdc.iloc[-1]['borrow_apy']:.2f}%")
    else:
        st.info("No Morpho data. Run collect_data.py.")

# --- Row 2: Spark + Compound ---
_rc3, _rc4 = st.columns(2)

with _rc3:
    _spark_path = _rates_data_dir / "spark_stable.csv"
    if _spark_path.exists():
        _spark_rates = pd.read_csv(_spark_path, parse_dates=["date"])
        _spark_rates = _spark_rates.rename(columns={"borrow_rate": "borrow_apy", "supply_rate": "supply_apy"})
        st.plotly_chart(
            _make_borrow_chart(_spark_rates, "Spark Lend", symbols=["USDC", "USDT", "DAI", "USDS"]),
            use_container_width=True,
        )
        _spark_usdc = _spark_rates[_spark_rates["symbol"] == "USDC"]
        if not _spark_usdc.empty:
            st.metric("USDC Borrow Now", f"{_spark_usdc.iloc[-1]['borrow_apy']:.2f}%")
    else:
        st.info("No Spark data. Run collect_data.py.")

with _rc4:
    _compound_path = _rates_data_dir / "compound_btc_borrow.csv"
    if _compound_path.exists():
        _compound_rates = pd.read_csv(_compound_path, parse_dates=["date"])
        # Filter to last 2 years to match other charts
        _two_years_ago = pd.Timestamp.now() - pd.DateOffset(years=2)
        _compound_rates = _compound_rates[_compound_rates["date"] >= _two_years_ago]
        st.plotly_chart(
            _make_borrow_chart(_compound_rates, "Compound V3"),
            use_container_width=True,
        )
        _compound_usdc = _compound_rates[_compound_rates["symbol"] == "USDC"]
        if not _compound_usdc.empty:
            st.metric("USDC Borrow Now", f"{_compound_usdc.iloc[-1]['borrow_apy']:.2f}%")
    else:
        st.info("No Compound data. Run collect_data.py.")

st.caption(
    "Source: Aave V3 ReserveParamsHistoryItem, Morpho Blue MarketDailySnapshot, "
    "Spark Lend marketDailySnapshot, Compound V3 weeklyMarketAccounting — all via The Graph. "
    "BTC price via DeFi Llama."
)

st.divider()

# =====================================================================
# 4. DeFi Integrations
# =====================================================================
st.header("4. DeFi Integrations")

st.caption(
    "**Methodology:** Exact token-level matching across DeFi Llama Yields API pools. "
    "Only active pools (TVL > $10k) counted. Metrics: unique protocols, active pools, chain diversity."
)

# Load fresh yields data for additional metrics (chain_count, active_pool_count)
_yields_path = _Path(__file__).parent / "data" / "defi_yields.json"
_yields_extra = {}
if _yields_path.exists():
    with open(_yields_path) as _f:
        _yields_raw = _json.load(_f)
    for _yr in _yields_raw:
        _yields_extra[_yr["name"]] = _yr

_int_col_left, _int_col_right = st.columns(2)

# --- LEFT: Protocols bar chart ---
with _int_col_left:
    st.subheader("Unique Protocols")
    integrations_df = df[df["name"].isin(FOCUS_COMPETITORS) & (df["integrations"] > 0)].sort_values("integrations", ascending=True).copy()

    if not integrations_df.empty:
        fig_int = px.bar(
            integrations_df,
            x="integrations", y="name", orientation="h",
            text="integrations",
            color_discrete_sequence=["#F7931A"],
        )
        fig_int.update_traces(textposition="outside", textfont_size=14)
        fig_int.update_layout(
            height=350,
            xaxis_title="Unique DeFi Protocols",
            xaxis=dict(title=dict(font=dict(size=14)), tickfont=dict(size=12)),
            yaxis_title="",
            yaxis=dict(tickfont=dict(size=13)),
            margin=dict(l=10, r=40, t=10, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig_int, use_container_width=True)
    else:
        st.info("No integration data. Run collect_data.py.")

# --- RIGHT: Chain diversity + pool count ---
with _int_col_right:
    st.subheader("Chain Diversity & Pool Count")

    _metrics_rows = []
    for _name in FOCUS_COMPETITORS:
        _extra = _yields_extra.get(_name, {})
        _metrics_rows.append({
            "name": _name,
            "chains": _extra.get("chain_count", 0),
            "pools": _extra.get("active_pool_count", 0),
            "pool_tvl": _extra.get("total_pool_tvl", 0),
        })
    _metrics_df = pd.DataFrame(_metrics_rows)
    _metrics_df = _metrics_df[_metrics_df["chains"] > 0].sort_values("chains", ascending=True)

    if not _metrics_df.empty:
        _fig_chains = go.Figure()

        # Chains bars
        _fig_chains.add_trace(go.Bar(
            y=_metrics_df["name"],
            x=_metrics_df["chains"],
            name="Chains",
            orientation="h",
            marker_color="#4ECDC4",
            text=_metrics_df["chains"],
            textposition="outside",
            textfont_size=14,
        ))

        _fig_chains.update_layout(
            height=350,
            xaxis_title="Number of Chains",
            xaxis=dict(title=dict(font=dict(size=14)), tickfont=dict(size=12)),
            yaxis_title="",
            yaxis=dict(tickfont=dict(size=13)),
            margin=dict(l=10, r=40, t=10, b=10),
            showlegend=False,
        )
        st.plotly_chart(_fig_chains, use_container_width=True)
    else:
        st.info("No chain data available.")

# Summary table below
if _yields_extra:
    _summary_rows = []
    for _name in FOCUS_COMPETITORS:
        _extra = _yields_extra.get(_name, {})
        _pool_tvl = _extra.get("total_pool_tvl", 0)
        _summary_rows.append({
            "Token": _name,
            "Protocols": _extra.get("defi_integrations_count", 0),
            "Active Pools": _extra.get("active_pool_count", 0),
            "Chains": _extra.get("chain_count", 0),
            "Pool TVL": f"${_pool_tvl / 1e9:.1f}B" if _pool_tvl >= 1e9 else f"${_pool_tvl / 1e6:.0f}M",
            "Top Integrations": ", ".join(_extra.get("top_integrations", [])[:5]),
        })
    st.dataframe(pd.DataFrame(_summary_rows), use_container_width=True, hide_index=True)

st.divider()

# =====================================================================
# 5. Competitive Radar
# =====================================================================
st.header("5. Competitive Radar")

radar_names = ["Babylon TBV"] + FOCUS_COMPETITORS
radar_df = df[df["name"].isin(radar_names)].copy()

if not radar_df.empty:
    def _safe_normalize(series):
        s = pd.to_numeric(series, errors="coerce").fillna(0)
        s_max = s.max()
        if s_max > 0:
            return s / s_max
        return s

    radar_df["self_custody_score"] = radar_df["self_custodial"].apply(lambda x: 1.0 if x else 0.0)
    radar_df["composability_score"] = _safe_normalize(
        pd.to_numeric(radar_df.get("defi_integrations_count", pd.Series(0, index=radar_df.index)), errors="coerce").fillna(0)
    )
    radar_df["tvl_score"] = _safe_normalize(
        np.log1p(pd.to_numeric(radar_df["effective_tvl"], errors="coerce").fillna(0))
    )

    if "holders_count" in radar_df.columns and radar_df["holders_count"].notna().any():
        radar_df["adoption_score"] = _safe_normalize(
            pd.to_numeric(radar_df["holders_count"], errors="coerce").fillna(0)
        )
    else:
        radar_df["adoption_score"] = radar_df["tvl_score"]

    radar_df["trust_score_norm"] = radar_df["custody_type"].map(TRUST_SCORES).fillna(1) / 4
    radar_df["efficiency_score"] = pd.to_numeric(
        radar_df.get("aave_ltv_onchain", pd.Series(0, index=radar_df.index)), errors="coerce"
    ).fillna(0) / 100

    categories = ["Self-Custody", "DeFi Reach", "TVL Scale", "Adoption", "Trust Level", "Capital Efficiency"]

    fig_radar = go.Figure()
    radar_colors = {
        "Babylon TBV": "#F7931A",
        "LBTC": "#4ECDC4", "sBTC": "#7B68EE", "tBTC": "#FF6B6B",
        "wBTC": "#45B7D1", "SolvBTC": "#98D8C8", "cbBTC": "#DDA0DD",
        "pumpBTC": "#E57373", "uniBTC": "#81C784", "FBTC": "#64B5F6",
        "Lorenzo stBTC": "#FFB74D", "coreBTC": "#A1887F", "eBTC": "#90A4AE",
    }

    for _, row in radar_df.iterrows():
        values = [
            row["self_custody_score"], row["composability_score"], row["tvl_score"],
            row["adoption_score"], row["trust_score_norm"], row["efficiency_score"],
        ]
        values.append(values[0])
        is_babylon = row["name"] == "Babylon TBV"

        fig_radar.add_trace(go.Scatterpolar(
            r=values,
            theta=categories + [categories[0]],
            fill="toself",
            name=row["name"],
            marker=dict(size=14 if is_babylon else 10),
            line=dict(
                color=radar_colors.get(row["name"], "#888"),
                width=5 if is_babylon else 3,
            ),
            opacity=0.9 if is_babylon else 0.5,
        ))

    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1], showticklabels=False, gridcolor="rgba(0,0,0,0.08)"),
            angularaxis=dict(tickfont=dict(size=18, color="#222")),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=750,
        margin=dict(t=60, b=60, l=120, r=120),
        legend=dict(font=dict(size=16)),
    )
    st.plotly_chart(fig_radar, use_container_width=True)

    st.caption(
        "Axes normalized 0-1. Self-Custody: binary. Trust Level: custody score / 4. "
        "Capital Efficiency: Aave LTV / 100. TVL & Adoption: log-normalized."
    )

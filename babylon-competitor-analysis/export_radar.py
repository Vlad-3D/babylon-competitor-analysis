"""Render three side-by-side radars (cbBTC, wBTC, Babylon TBV) for the
Babylon TBV fee strategy doc.

Run:  uv run python export_radar.py
Output: radar.png in repo root.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.aggregate import aggregate_all
from src.static_metadata import TRUST_SCORES

OUT_PATH = Path(__file__).parent.parent / "radar.png"

CATEGORIES = [
    "Self-Custody", "DeFi Reach", "TVL Scale",
    "Adoption", "Trust Level", "Capital Efficiency",
]

COLORS = {
    "cbBTC": "#DDA0DD",
    "wBTC": "#45B7D1",
    "Babylon TBV": "#F7931A",
}

BABYLON_TARGET = {
    "Self-Custody": 1.0,
    "DeFi Reach": 0.15,
    "TVL Scale": 0.15,
    "Adoption": 0.10,
    "Trust Level": 1.0,
    "Capital Efficiency": 0.78,
}


def _safe_normalize(series):
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    s_max = s.max()
    if s_max > 0:
        return s / s_max
    return s


def compute_scores():
    """Compute normalised radar scores for all focus competitors."""
    df, _ = aggregate_all()
    focus = ["wBTC", "cbBTC", "LBTC", "tBTC"]
    rd = df[df["name"].isin(focus)].copy()

    rd["Self-Custody"] = rd["self_custodial"].apply(lambda x: 1.0 if x else 0.0)
    rd["DeFi Reach"] = _safe_normalize(
        pd.to_numeric(rd.get("defi_integrations_count", pd.Series(0, index=rd.index)), errors="coerce").fillna(0)
    )
    rd["TVL Scale"] = _safe_normalize(
        np.log1p(pd.to_numeric(rd["effective_tvl"], errors="coerce").fillna(0))
    )
    if "holders_count" in rd.columns and rd["holders_count"].notna().any():
        rd["Adoption"] = _safe_normalize(
            pd.to_numeric(rd["holders_count"], errors="coerce").fillna(0)
        )
    else:
        rd["Adoption"] = rd["TVL Scale"]
    rd["Trust Level"] = rd["custody_type"].map(TRUST_SCORES).fillna(1) / 4
    rd["Capital Efficiency"] = pd.to_numeric(
        rd.get("aave_ltv_onchain", pd.Series(0, index=rd.index)), errors="coerce"
    ).fillna(0) / 100

    scores = {}
    for _, row in rd.iterrows():
        scores[row["name"]] = {cat: float(row[cat]) for cat in CATEGORIES}
    scores["Babylon TBV"] = BABYLON_TARGET
    return scores


def add_radar(fig, scores_dict, name, row, col):
    color = COLORS.get(name, "#888")
    values = [scores_dict[cat] for cat in CATEGORIES]
    values.append(values[0])
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=CATEGORIES + [CATEGORIES[0]],
        fill="toself",
        name=name,
        marker=dict(size=8, color=color),
        line=dict(color=color, width=3),
        opacity=0.85,
        fillcolor=color,
        showlegend=False,
    ), row=row, col=col)


def main():
    scores = compute_scores()

    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{"type": "polar"}, {"type": "polar"}, {"type": "polar"}]],
        subplot_titles=("cbBTC", "wBTC", "Babylon TBV (target)"),
        horizontal_spacing=0.14,
    )

    add_radar(fig, scores["cbBTC"], "cbBTC", 1, 1)
    add_radar(fig, scores["wBTC"], "wBTC", 1, 2)
    add_radar(fig, scores["Babylon TBV"], "Babylon TBV", 1, 3)

    # Apply consistent styling to all three polar axes without overriding
    # the per-subplot domain (which make_subplots computes automatically).
    fig.update_polars(
        radialaxis=dict(visible=True, range=[0, 1], showticklabels=False, gridcolor="rgba(0,0,0,0.12)", nticks=5),
        angularaxis=dict(tickfont=dict(size=11, color="#222")),
        bgcolor="white",
    )

    fig.update_layout(
        height=600,
        width=1800,
        margin=dict(t=90, b=50, l=80, r=80),
        title=dict(
            text="Competitive Radar: Babylon TBV vs major BTC tokens",
            x=0.5, font=dict(size=22),
        ),
        paper_bgcolor="white",
    )

    # Subplot title font size
    for ann in fig.layout.annotations:
        ann.font = dict(size=16, color="#222")

    fig.write_image(str(OUT_PATH), scale=2)
    print(f"Saved 3-panel radar to {OUT_PATH}")


if __name__ == "__main__":
    main()

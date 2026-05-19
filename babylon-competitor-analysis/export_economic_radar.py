"""Economic competitive radar — one panel per protocol, side-by-side, so the
shapes are directly comparable (same axes/scale, no overlay clutter).

Run:  uv run python export_economic_radar.py
Output: economic_radar.png in repo root.
"""

from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUT_PATH = Path(__file__).parent.parent / "economic_radar.png"

# ---------- Verified data (from each protocol's own docs) ----------
PROTOCOLS = {
    "Aave V3": {
        "avail_usdc_m": 137,
        "liq_point_pct": 78,
        "protection": 0.60,
        "rate_pct": 4.53,
        "color": "#90C2E7",
    },
    "Aave V4 default": {
        "avail_usdc_m": 137,
        "liq_point_pct": 78,
        "protection": 0.85,
        "rate_pct": 4.50,
        "color": "#1E40AF",
    },
    "Spark Lend": {
        "avail_usdc_m": 4,
        "liq_point_pct": 78,
        "protection": 0.55,
        "rate_pct": 4.56,
        "color": "#F5AC37",
    },
    "Compound V3": {
        "avail_usdc_m": 33,
        "liq_point_pct": 85,
        "protection": 0.35,
        "rate_pct": 4.05,
        "color": "#00B377",
    },
    "Morpho Blue": {
        "avail_usdc_m": 150,
        "liq_point_pct": 86,
        "protection": 0.15,
        "rate_pct": 3.73,
        "color": "#7B68EE",
    },
    "Babylon TBV (target)": {
        "avail_usdc_m": 200,
        "liq_point_pct": 80,
        "protection": 0.95,
        "rate_pct": 4.50,
        "color": "#F7931A",
    },
}

CATEGORIES = [
    "Liquidation Point",
    "Borrower Protection",
    "Lower Borrow Rate",
    "Available USDC",
]


def normalize(p):
    return [
        max(0, min(1, (p["liq_point_pct"] - 70) / (90 - 70))),
        p["protection"],
        max(0, min(1, (6 - p["rate_pct"]) / (6 - 3))),
        max(0, min(1, p["avail_usdc_m"] / 300)),
    ]


def panel_subtitle(name, p):
    return (
        f"<b>{name}</b><br>"
        f"<span style='font-size:11px;color:#666'>"
        f"LiqPt {p['liq_point_pct']}%  ·  "
        f"Avail ${p['avail_usdc_m']}M  ·  "
        f"Rate {p['rate_pct']}%</span>"
    )


def main():
    names = list(PROTOCOLS.keys())
    fig = make_subplots(
        rows=2, cols=3,
        specs=[
            [{"type": "polar"}, {"type": "polar"}, {"type": "polar"}],
            [{"type": "polar"}, {"type": "polar"}, {"type": "polar"}],
        ],
        subplot_titles=[panel_subtitle(n, PROTOCOLS[n]) for n in names],
        horizontal_spacing=0.12,
        vertical_spacing=0.18,
    )

    positions = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)]
    for (row, col), name in zip(positions, names):
        p = PROTOCOLS[name]
        values = normalize(p)
        values.append(values[0])
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=CATEGORIES + [CATEGORIES[0]],
            fill="toself",
            name=name,
            marker=dict(size=8, color=p["color"]),
            line=dict(color=p["color"], width=3),
            opacity=0.85,
            fillcolor=p["color"],
            showlegend=False,
        ), row=row, col=col)

    fig.update_polars(
        radialaxis=dict(visible=True, range=[0, 1], showticklabels=False,
                        gridcolor="rgba(0,0,0,0.12)", nticks=5),
        angularaxis=dict(tickfont=dict(size=10, color="#222")),
        bgcolor="white",
    )

    fig.update_layout(
        height=900,
        width=1600,
        margin=dict(t=110, b=40, l=60, r=60),
        title=dict(
            text="Economic radar: BTC-collateral lending venues vs Babylon TBV target",
            x=0.5, font=dict(size=20),
        ),
        paper_bgcolor="white",
    )

    for ann in fig.layout.annotations:
        ann.font = dict(size=14, color="#222")
        ann.yshift = 22

    fig.write_image(str(OUT_PATH), scale=2)
    print(f"Saved 6-panel economic radar to {OUT_PATH}")


if __name__ == "__main__":
    main()

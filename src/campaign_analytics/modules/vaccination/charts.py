"""Plotly charts for one vaccine analysis at a time.

Each function produces a single, self-contained Plotly figure for one vaccine
only.  The platform's shared chart theme is applied automatically.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from campaign_analytics.components.charts import CHART_COLORS, apply_chart_theme

# ── Colour constants ─────────────────────────────────────────────────────────
_COV_HIGH = "#0B6E69"      # ≥ 90 %  (teal / on-target)
_COV_MED = "#E18B28"       # 50–89 % (amber / needs attention)
_COV_LOW = "#D45572"       # < 50 %  (red / critical)
_VACCINATED_CLR = "#2878B5"
_REMAINING_CLR = "#D0D5DD"
_REFERENCE_CLR = "#667085"


def _coverage_colour(pct: float | None) -> str:
    """Return a semantic colour for a coverage percentage."""
    if pct is None:
        return _COV_LOW
    if pct >= 90:
        return _COV_HIGH
    if pct >= 50:
        return _COV_MED
    return _COV_LOW


# ── Coverage by LGA (horizontal bar) ─────────────────────────────────────────

def coverage_by_lga(data: pd.DataFrame, vaccine_label: str) -> go.Figure:
    """Horizontal bar chart of LGA coverage for one vaccine.

    Includes a 90 % target reference line and per-bar colour coding based
    on coverage thresholds.
    """
    sorted_data = data.sort_values("Coverage (%)", ascending=True).copy()
    bar_colours = [_coverage_colour(v) for v in sorted_data["Coverage (%)"]]

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=sorted_data["Coverage (%)"],
            y=sorted_data["LGA"],
            orientation="h",
            marker_color=bar_colours,
            text=[
                f"{v:.1f}%" if pd.notna(v) else "–"
                for v in sorted_data["Coverage (%)"]
            ],
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Coverage: %{x:.1f}%<br>"
                "<extra></extra>"
            ),
        )
    )

    # 90 % target reference line
    figure.add_vline(
        x=90,
        line_dash="dot",
        line_color=_REFERENCE_CLR,
        line_width=1.5,
        annotation_text="90 % target",
        annotation_position="top right",
        annotation_font_size=10,
        annotation_font_color=_REFERENCE_CLR,
    )

    max_val = float(sorted_data["Coverage (%)"].max()) if not sorted_data.empty else 100
    figure.update_xaxes(
        range=[0, max(105, max_val * 1.15)],
        title_text="Coverage (%)",
    )
    figure.update_yaxes(title_text="")
    figure.update_layout(title_text=f"{vaccine_label} — Coverage by LGA")

    dynamic_height = max(360, min(720, len(sorted_data) * 38))
    return apply_chart_theme(figure, height=dynamic_height)


# ── Vaccinated vs Remaining (stacked bar) ────────────────────────────────────

def vaccinated_vs_remaining(data: pd.DataFrame, vaccine_label: str) -> go.Figure:
    """Stacked bar chart showing vaccinated and remaining children per LGA."""
    sorted_data = data.sort_values("LGA")

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=sorted_data["LGA"],
            y=sorted_data["Vaccinated"],
            name="Vaccinated",
            marker_color=_VACCINATED_CLR,
            hovertemplate="<b>%{x}</b><br>Vaccinated: %{y:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            x=sorted_data["LGA"],
            y=sorted_data["Remaining"],
            name="Remaining",
            marker_color=_REMAINING_CLR,
            hovertemplate="<b>%{x}</b><br>Remaining: %{y:,.0f}<extra></extra>",
        )
    )
    figure.update_layout(
        barmode="stack",
        title_text=f"{vaccine_label} — Vaccinated vs Remaining",
        xaxis_title="LGA",
        yaxis_title="Children",
    )
    return apply_chart_theme(figure, height=400)


# ── Coverage gauge ────────────────────────────────────────────────────────────

def coverage_gauge(coverage_pct: float | None, vaccine_label: str) -> go.Figure:
    """Semicircular gauge showing overall coverage percentage for one vaccine."""
    value = coverage_pct if coverage_pct is not None else 0
    colour = _coverage_colour(coverage_pct)

    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"suffix": "%", "font": {"size": 36, "color": colour}},
            gauge={
                "axis": {"range": [0, 100], "ticksuffix": "%"},
                "bar": {"color": colour, "thickness": 0.6},
                "bgcolor": "#F2F4F7",
                "steps": [
                    {"range": [0, 50], "color": "#FEF3F2"},
                    {"range": [50, 90], "color": "#FFFAEB"},
                    {"range": [90, 100], "color": "#ECFDF3"},
                ],
                "threshold": {
                    "line": {"color": _REFERENCE_CLR, "width": 2},
                    "thickness": 0.8,
                    "value": 90,
                },
            },
            title={"text": f"{vaccine_label} Overall Coverage"},
        )
    )
    return apply_chart_theme(figure, height=260)

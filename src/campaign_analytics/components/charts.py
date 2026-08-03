"""Shared Plotly formatting and chart states."""

import plotly.graph_objects as go


CHART_COLORS = ["#0B6E69", "#2878B5", "#7C5CE0", "#E18B28", "#D45572"]


def apply_chart_theme(figure: go.Figure, height: int = 360) -> go.Figure:
    """Apply the platform's visual language to a Plotly figure."""
    figure.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=36, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#344054", family="Inter, sans-serif"),
        colorway=CHART_COLORS,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    figure.update_xaxes(showgrid=True, gridcolor="#EAECF0", zeroline=False)
    figure.update_yaxes(showgrid=False, zeroline=False)
    return figure


def empty_chart(title: str, message: str) -> go.Figure:
    """Return a Plotly empty state for charts awaiting validated module results."""
    figure = go.Figure()
    figure.add_annotation(
        text=f"<b>{title}</b><br><span style='font-size:12px'>{message}</span>",
        showarrow=False,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        align="center",
        font=dict(color="#667085"),
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return apply_chart_theme(figure, height=250)


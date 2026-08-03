"""Plotly charts for LGA-level Teams Reporting results."""

import pandas as pd
import plotly.express as px

from campaign_analytics.components.charts import apply_chart_theme


def reporting_rate_by_lga(data: pd.DataFrame):
    """Return an interactive ranked LGA reporting-rate chart."""
    figure = px.bar(
        data.sort_values("reporting_percent", ascending=True),
        x="reporting_percent",
        y="lga",
        orientation="h",
        color_discrete_sequence=["#0B6E69"],
        labels={"reporting_percent": "Reporting (%)", "lga": "LGA"},
        hover_data={
            "planned_teams": ":,.0f",
            "teams_reported": ":,.0f",
            "missing_teams": ":,.0f",
            "reporting_percent": ".1f",
        },
        title="Team reporting rate by LGA",
    )
    figure.update_xaxes(
        range=[0, max(100, float(data["reporting_percent"].max()) * 1.1)]
    )
    return apply_chart_theme(figure, height=max(340, min(720, len(data) * 36)))


def team_status_by_lga(data: pd.DataFrame):
    """Return planned, reported, and missing-team comparison by LGA."""
    chart_data = data.melt(
        id_vars=["lga"],
        value_vars=["planned_teams", "teams_reported", "missing_teams"],
        var_name="metric",
        value_name="teams",
    )
    figure = px.bar(
        chart_data,
        x="lga",
        y="teams",
        color="metric",
        barmode="group",
        color_discrete_map={
            "planned_teams": "#B8C2CC",
            "teams_reported": "#2878B5",
            "missing_teams": "#D45572",
        },
        labels={"lga": "LGA", "teams": "Teams", "metric": "Metric"},
        title="Planned, reported, and missing teams",
    )
    return apply_chart_theme(figure, height=390)


"""Plotly visualization functions for Settlement Analysis."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from campaign_analytics.modules.settlement_analysis.processor import SettlementAnalysisSummary


def build_source_coverage_chart(summary: SettlementAnalysisSummary) -> go.Figure:
    """Build horizontal bar chart comparing visitation coverage by source."""
    sources = [
        "GTS Visitation",
        "eTally Visitation",
        "MST Visitation",
        "MST + eTally Combined",
        "Any Source Visited",
        "All Sources Visited",
    ]
    percentages = [
        summary.gts_coverage_pct or 0.0,
        summary.etally_coverage_pct or 0.0,
        summary.mst_coverage_pct or 0.0,
        summary.mst_etally_coverage_pct or 0.0,
        summary.any_source_coverage_pct or 0.0,
        summary.all_sources_coverage_pct or 0.0,
    ]
    counts = [
        summary.gts_visited_count,
        summary.etally_visited_count,
        summary.mst_visited_count,
        summary.mst_etally_visited_count,
        summary.any_source_visited_count,
        summary.all_sources_visited_count,
    ]

    df_chart = pd.DataFrame({
        "Source": sources,
        "Coverage %": percentages,
        "Visited Settlements": counts,
    })

    fig = px.bar(
        df_chart,
        x="Coverage %",
        y="Source",
        orientation="h",
        text=df_chart.apply(lambda r: f"{r['Coverage %']}% ({r['Visited Settlements']:,})", axis=1),
        title="Settlement Visitation Coverage by Tracking Source",
        color="Coverage %",
        color_continuous_scale="Viridis",
    )
    fig.update_layout(
        xaxis=dict(range=[0, 105], title="Coverage Percentage (%)"),
        yaxis=dict(autorange="reversed"),
        height=350,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False,
    )
    return fig


def build_lga_coverage_chart(df_lga: pd.DataFrame) -> go.Figure:
    """Build grouped bar chart comparing coverage percentages by LGA."""
    if df_lga.empty:
        fig = go.Figure()
        fig.update_layout(title="No LGA Data Available")
        return fig

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_lga["LGA"],
        y=df_lga["GTS Coverage %"],
        name="GTS Coverage %",
        marker_color="#1f77b4",
    ))
    fig.add_trace(go.Bar(
        x=df_lga["LGA"],
        y=df_lga["eTally Coverage %"],
        name="eTally Coverage %",
        marker_color="#ff7f0e",
    ))
    fig.add_trace(go.Bar(
        x=df_lga["LGA"],
        y=df_lga["MST Coverage %"],
        name="MST Coverage %",
        marker_color="#2ca02c",
    ))

    fig.update_layout(
        title="Coverage Percentage Comparison by LGA",
        barmode="group",
        xaxis_title="Local Government Area (LGA)",
        yaxis_title="Coverage %",
        yaxis=dict(range=[0, 105]),
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=40),
    )
    return fig


def build_status_distribution_chart(df_linelist: pd.DataFrame) -> go.Figure:
    """Build donut chart showing overall visitation status breakdown."""
    if df_linelist.empty or "Overall_Visitation_Status" not in df_linelist.columns:
        fig = go.Figure()
        fig.update_layout(title="No Data")
        return fig

    counts = df_linelist["Overall_Visitation_Status"].value_counts().reset_index()
    counts.columns = ["Status", "Count"]

    fig = px.pie(
        counts,
        names="Status",
        values="Count",
        hole=0.4,
        title="Overall Settlement Visitation Status Breakdown",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        height=380,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig

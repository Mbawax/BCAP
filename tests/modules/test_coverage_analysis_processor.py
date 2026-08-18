"""Unit tests for Coverage Analysis processor (absolute percentage formatting)."""

import pandas as pd
from campaign_analytics.modules.coverage_analysis.processor import (
    _coerce_numeric,
    build_settlement_master,
    build_ward_summary,
    CoverageAnalysisSummary,
)
from campaign_analytics.modules.coverage_analysis.ui import format_pct


def test_coerce_numeric_absolute_percentage():
    s = pd.Series(["10.1%", "60.5%", "99.9%"])
    coerced = _coerce_numeric(s)
    # Coerced values should be rounded to absolute integers (0 decimals)
    assert coerced.tolist() == [10.0, 60.0, 100.0]


def test_format_pct_absolute_percentage():
    assert format_pct(10.1) == "10%"
    assert format_pct(60.6) == "61%"
    assert format_pct(99.9) == "100%"
    assert format_pct(None) == "N/A"
    assert format_pct(pd.NA) == "N/A"


def test_coverage_master_and_ward_summary_absolute_percentages():
    df_vacc = pd.DataFrame({
        "LGA": ["LGA1", "LGA1", "LGA1"],
        "Ward": ["WardA", "WardA", "WardA"],
        "Settlement": ["S1", "S2", "S3"],
        "Vaccination Coverage %": [10.1, 20.4, 30.6],
    })
    vacc_mapping = {
        "lga": "LGA",
        "ward": "Ward",
        "settlement": "Settlement",
        "vaccination_coverage": "Vaccination Coverage %",
    }

    summary, master = build_settlement_master(
        df_vaccination=df_vacc,
        vaccination_mapping=vacc_mapping,
    )

    # Master table indicator values should be integer rounded
    assert master["% Vaccination"].tolist() == [10.0, 20.0, 31.0]

    ward_summary = build_ward_summary(master)
    # Ward-level average should be rounded to integer percentage
    assert ward_summary["% Vaccination"].iloc[0] == 20.0

"""Unit tests for LGA Coverage Analysis processor."""

import pandas as pd
from campaign_analytics.modules.coverage_analysis.processor import (
    DEFAULT_THRESHOLDS,
)
from campaign_analytics.modules.lga_coverage_analysis.processor import (
    COL_HOUSEHOLD,
    COL_LGA,
    COL_VACCINATION,
    COL_VISITATION,
    build_lga_master,
    detect_lga_operational_issues,
    generate_lga_coverage_excel_report,
    suggest_lga_household_mapping,
    suggest_lga_vaccination_mapping,
    suggest_lga_visitation_mapping,
    validate_lga_inputs,
)
from campaign_analytics.modules.lga_coverage_analysis.ui import format_pct


def test_suggest_mappings():
    cols_vacc = ["LGA_Name", "Coverage_Percent"]
    mapping_vacc = suggest_lga_vaccination_mapping(cols_vacc)
    assert mapping_vacc["lga"] == "LGA_Name"
    assert mapping_vacc["vaccination_coverage"] == "Coverage_Percent"

    cols_hh = ["LGA", "Household_Coverage"]
    mapping_hh = suggest_lga_household_mapping(cols_hh)
    assert mapping_hh["lga"] == "LGA"
    assert mapping_hh["household_coverage"] == "Household_Coverage"

    cols_vis = ["District", "Visitation_Pct"]
    mapping_vis = suggest_lga_visitation_mapping(cols_vis)
    assert mapping_vis["lga"] == "District"
    assert mapping_vis["visitation_coverage"] == "Visitation_Pct"


def test_validate_lga_inputs():
    df_vacc = pd.DataFrame({"LGA": ["Maiduguri"], "Vacc": [85.0]})
    # Missing required mapping
    report = validate_lga_inputs(df_vacc, {"lga": "LGA", "vaccination_coverage": None})
    assert not report.is_valid

    # Valid mapping
    report = validate_lga_inputs(df_vacc, {"lga": "LGA", "vaccination_coverage": "Vacc"})
    assert report.is_valid


def test_build_lga_master_and_summary():
    df_vacc = pd.DataFrame({
        "LGA": ["Maiduguri", "Jere", "Bama"],
        "Vacc_Cov": [85.4, 60.1, 45.8],
    })
    vacc_mapping = {"lga": "LGA", "vaccination_coverage": "Vacc_Cov"}

    df_hh = pd.DataFrame({
        "LGA": ["Maiduguri", "Jere", "Bama"],
        "HH_Cov": ["90%", "70%", "30%"],
    })
    hh_mapping = {"lga": "LGA", "household_coverage": "HH_Cov"}

    df_vis = pd.DataFrame({
        "LGA": ["Maiduguri", "Jere"],
        "Vis_Cov": [100, 80],
    })
    vis_mapping = {"lga": "LGA", "visitation_coverage": "Vis_Cov"}

    summary, master = build_lga_master(
        df_vaccination=df_vacc,
        vaccination_mapping=vacc_mapping,
        df_household=df_hh,
        household_mapping=hh_mapping,
        df_visitation=df_vis,
        visitation_mapping=vis_mapping,
    )

    assert summary.total_lgas == 3
    # Check absolute percentage rounding in master table
    assert master[COL_VACCINATION].tolist() == [85.0, 60.0, 46.0]
    assert master[COL_HOUSEHOLD].tolist() == [90.0, 70.0, 30.0]
    assert master[COL_VISITATION].iloc[0] == 100.0
    assert pd.isna(master[COL_VISITATION].iloc[2])


def test_detect_lga_operational_issues():
    df_lga = pd.DataFrame({
        COL_LGA: ["LGA1", "LGA2"],
        COL_VISITATION: [100.0, 40.0],
        COL_VACCINATION: [30.0, 85.0],
        COL_HOUSEHOLD: [80.0, 90.0],
    })
    issues = detect_lga_operational_issues(df_lga, DEFAULT_THRESHOLDS)
    assert not issues.empty
    # LGA1 has High Visitation (100 >= 70) + Low Vaccination (30 < 49)
    lga1_issues = issues[issues[COL_LGA] == "LGA1"]["Issue Type"].tolist()
    assert "High Visitation + Low Vaccination" in lga1_issues


def test_generate_lga_coverage_excel_report():
    df_vacc = pd.DataFrame({
        "LGA": ["Maiduguri"],
        "Vacc_Cov": [85.0],
    })
    vacc_mapping = {"lga": "LGA", "vaccination_coverage": "Vacc_Cov"}
    summary, master = build_lga_master(df_vacc, vacc_mapping)
    issues = detect_lga_operational_issues(master, DEFAULT_THRESHOLDS)

    excel_bytes = generate_lga_coverage_excel_report(
        summary, master, DEFAULT_THRESHOLDS, issues
    )
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0


def test_format_pct():
    assert format_pct(10.1) == "10%"
    assert format_pct(60.6) == "61%"
    assert format_pct(None) == "N/A"

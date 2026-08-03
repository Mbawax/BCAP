"""Unit tests for the Settlement Analysis processing engine."""

import io

import pandas as pd
import pytest

from campaign_analytics.modules.settlement_analysis.processor import (
    build_unique_id,
    generate_settlement_excel_report,
    process_settlement_analysis,
    suggest_settlement_mapping,
    validate_inputs,
)


def test_suggest_settlement_mapping():
    cols = ["LGA_Name", "Ward_Name", "Settlement_Name", "Population"]
    mapping = suggest_settlement_mapping(cols)
    assert mapping["lga"] == "LGA_Name"
    assert mapping["ward"] == "Ward_Name"
    assert mapping["settlement"] == "Settlement_Name"


def test_build_unique_id():
    df = pd.DataFrame({
        "LGA": [" Maiduguri ", "BAMA"],
        "Ward": ["Bolori 1", " Central "],
        "Settlement": ["Hausari", "Shehuri"],
    })
    ids = build_unique_id(df, "LGA", "Ward", "Settlement")
    assert ids.iloc[0] == "MAIDUGURI_BOLORI 1_HAUSARI"
    assert ids.iloc[1] == "BAMA_CENTRAL_SHEHURI"


def test_validate_inputs_empty():
    report = validate_inputs(None, {})
    assert not report.is_valid
    assert "Planned Settlements dataset (baseline) is required." in report.errors[0]


def test_process_settlement_analysis_triangulation():
    # 1. Planned baseline (3 settlements across 2 LGAs)
    df_planned = pd.DataFrame({
        "LGA": ["Maiduguri", "Maiduguri", "Bama"],
        "Ward": ["Ward A", "Ward B", "Ward C"],
        "Settlement": ["Settlement 1", "Settlement 2", "Settlement 3"],
        "Target_Pop": [100, 200, 150],
    })
    p_map = {"lga": "LGA", "ward": "Ward", "settlement": "Settlement"}

    # 2. GTS dataset (visiting Settlement 1 and Settlement 2)
    df_gts = pd.DataFrame({
        "LGA": ["Maiduguri", "Maiduguri"],
        "Ward": ["Ward A", "Ward B"],
        "Settlement": ["Settlement 1", "Settlement 2"],
        "GTS_GPS_Track": ["OK", "OK"],
    })
    g_map = {"lga": "LGA", "ward": "Ward", "settlement": "Settlement"}

    # 3. eTally dataset (visiting Settlement 1)
    df_etally = pd.DataFrame({
        "LGA": ["Maiduguri"],
        "Ward": ["Ward A"],
        "Settlement": ["Settlement 1"],
    })
    e_map = {"lga": "LGA", "ward": "Ward", "settlement": "Settlement"}

    # 4. MST dataset (visiting Settlement 1 and Settlement 3)
    df_mst = pd.DataFrame({
        "LGA": ["Maiduguri", "Bama"],
        "Ward": ["Ward A", "Ward C"],
        "Settlement": ["Settlement 1", "Settlement 3"],
    })
    m_map = {"lga": "LGA", "ward": "Ward", "settlement": "Settlement"}

    summary, df_lga, df_linelist = process_settlement_analysis(
        df_planned=df_planned,
        planned_mapping=p_map,
        df_gts=df_gts,
        gts_mapping=g_map,
        df_etally=df_etally,
        etally_mapping=e_map,
        df_mst=df_mst,
        mst_mapping=m_map,
    )

    # Check Summary KPIs
    assert summary.total_planned == 3
    assert summary.gts_visited_count == 2
    assert summary.etally_visited_count == 1
    assert summary.mst_visited_count == 2
    assert summary.all_sources_visited_count == 1  # Settlement 1 is visited by all 3
    assert summary.any_source_visited_count == 3  # All 3 settlements visited by at least one
    assert summary.unvisited_count == 0

    # Check Linelist
    s1 = df_linelist[df_linelist["Settlement"] == "Settlement 1"].iloc[0]
    assert s1["GTS_Visited"] == "Visited"
    assert s1["eTally_Visited"] == "Visited"
    assert s1["MST_Visited"] == "Visited"
    assert s1["MST_eTally_Combined"] == "Both MST & eTally"
    assert s1["Overall_Visitation_Status"] == "Visited by All (GTS + eTally + MST)"

    s2 = df_linelist[df_linelist["Settlement"] == "Settlement 2"].iloc[0]
    assert s2["GTS_Visited"] == "Visited"
    assert s2["eTally_Visited"] == "Not Visited"
    assert s2["MST_Visited"] == "Not Visited"
    assert s2["MST_eTally_Combined"] == "Neither"
    assert s2["Overall_Visitation_Status"] == "GTS Only"

    s3 = df_linelist[df_linelist["Settlement"] == "Settlement 3"].iloc[0]
    assert s3["GTS_Visited"] == "Not Visited"
    assert s3["eTally_Visited"] == "Not Visited"
    assert s3["MST_Visited"] == "Visited"
    assert s3["MST_eTally_Combined"] == "MST Only"
    assert s3["Overall_Visitation_Status"] == "MST Only"

    # Check Excel Multi-Sheet Generation
    excel_bytes = generate_settlement_excel_report(summary, df_lga, df_linelist)
    assert len(excel_bytes) > 0

    # Verify sheet names in generated Excel file
    excel_file = pd.ExcelFile(io.BytesIO(excel_bytes))
    assert "Campaign Summary" in excel_file.sheet_names
    assert "LGA Coverage & Summary" in excel_file.sheet_names
    assert "Settlement Linelist" in excel_file.sheet_names

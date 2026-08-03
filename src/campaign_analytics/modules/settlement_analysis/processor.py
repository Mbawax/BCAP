"""Pure data processing engine for Settlement Analysis & Triangulation."""

from dataclasses import dataclass, field
from io import BytesIO
import re
from typing import TypeAlias

import pandas as pd

MappingDict: TypeAlias = dict[str, str | None]

REQUIRED_FIELDS = ("lga", "ward", "settlement")


@dataclass(slots=True)
class ValidationReport:
    """Validation outcome for Settlement Analysis inputs."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return whether required data is valid for processing."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class SettlementAnalysisSummary:
    """Campaign-level KPIs for Settlement Analysis."""

    total_planned: int
    gts_visited_count: int
    gts_coverage_pct: float | None
    etally_visited_count: int
    etally_coverage_pct: float | None
    mst_visited_count: int
    mst_coverage_pct: float | None
    mst_etally_visited_count: int
    mst_etally_coverage_pct: float | None
    all_sources_visited_count: int
    all_sources_coverage_pct: float | None
    any_source_visited_count: int
    any_source_coverage_pct: float | None
    unvisited_count: int
    unvisited_pct: float | None
    lga_count: int


def _normalise_name(name: str) -> str:
    """Normalise string for fuzzy matching (strip non-alphanumeric, lowercase)."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def suggest_settlement_mapping(columns: list[str]) -> MappingDict:
    """Suggest column mappings for LGA, Ward, and Settlement from column names."""
    normalised = {_normalise_name(col): col for col in columns}

    aliases = {
        "lga": ("lga", "localgovernmentarea", "district", "lga_name", "lganame"),
        "ward": ("ward", "ward_name", "wardname", "subdistrict"),
        "settlement": ("settlement", "settlement_name", "settlementname", "community", "village"),
    }

    return {
        field_key: next((normalised[name] for name in names if name in normalised), None)
        for field_key, names in aliases.items()
    }


def normalize_text_series(series: pd.Series) -> pd.Series:
    """Clean and standardize text fields for exact key creation."""
    return series.fillna("").astype(str).str.strip().str.upper()


def build_unique_id(
    df: pd.DataFrame, lga_col: str, ward_col: str, settlement_col: str
) -> pd.Series:
    """Create a composite unique identifier (LGA_Ward_Settlement) for triangulation."""
    lga = normalize_text_series(df[lga_col])
    ward = normalize_text_series(df[ward_col])
    settlement = normalize_text_series(df[settlement_col])
    return lga + "_" + ward + "_" + settlement


def validate_inputs(
    df_planned: pd.DataFrame | None,
    planned_mapping: MappingDict,
    df_gts: pd.DataFrame | None = None,
    gts_mapping: MappingDict | None = None,
    df_etally: pd.DataFrame | None = None,
    etally_mapping: MappingDict | None = None,
    df_mst: pd.DataFrame | None = None,
    mst_mapping: MappingDict | None = None,
) -> ValidationReport:
    """Validate uploaded dataframes and field mappings for Settlement Analysis."""
    report = ValidationReport()

    if df_planned is None or df_planned.empty:
        report.errors.append("Planned Settlements dataset (baseline) is required.")
        return report

    # Check baseline planned mapping
    for field_key in REQUIRED_FIELDS:
        mapped_col = planned_mapping.get(field_key)
        if not mapped_col:
            report.errors.append(f"Planned Settlements mapping missing for '{field_key.upper()}'.")
        elif mapped_col not in df_planned.columns:
            report.errors.append(
                f"Column '{mapped_col}' mapped to '{field_key.upper()}' not found in Planned Settlements dataset."
            )

    # Check GTS mapping if uploaded
    if df_gts is not None and not df_gts.empty and gts_mapping:
        for field_key in REQUIRED_FIELDS:
            mapped_col = gts_mapping.get(field_key)
            if mapped_col and mapped_col not in df_gts.columns:
                report.errors.append(
                    f"Column '{mapped_col}' mapped to '{field_key.upper()}' not found in GTS Visitation dataset."
                )

    # Check eTally mapping if uploaded
    if df_etally is not None and not df_etally.empty and etally_mapping:
        for field_key in REQUIRED_FIELDS:
            mapped_col = etally_mapping.get(field_key)
            if mapped_col and mapped_col not in df_etally.columns:
                report.errors.append(
                    f"Column '{mapped_col}' mapped to '{field_key.upper()}' not found in eTally dataset."
                )

    # Check MST mapping if uploaded
    if df_mst is not None and not df_mst.empty and mst_mapping:
        for field_key in REQUIRED_FIELDS:
            mapped_col = mst_mapping.get(field_key)
            if mapped_col and mapped_col not in df_mst.columns:
                report.errors.append(
                    f"Column '{mapped_col}' mapped to '{field_key.upper()}' not found in MST dataset."
                )

    if not any([
        df_gts is not None and not df_gts.empty,
        df_etally is not None and not df_etally.empty,
        df_mst is not None and not df_mst.empty,
    ]):
        report.warnings.append(
            "No visitation tracking dataset (GTS, eTally, or MST) uploaded yet. All planned settlements will mark as Not Visited."
        )

    return report


def process_settlement_analysis(
    df_planned: pd.DataFrame,
    planned_mapping: MappingDict,
    df_gts: pd.DataFrame | None = None,
    gts_mapping: MappingDict | None = None,
    df_etally: pd.DataFrame | None = None,
    etally_mapping: MappingDict | None = None,
    df_mst: pd.DataFrame | None = None,
    mst_mapping: MappingDict | None = None,
) -> tuple[SettlementAnalysisSummary, pd.DataFrame, pd.DataFrame]:
    """Triangulate visitation sources against Planned Settlements baseline.

    Returns:
        (summary_kpis, df_lga_summary, df_settlement_linelist)
    """
    p_lga = planned_mapping["lga"]
    p_ward = planned_mapping["ward"]
    p_settlement = planned_mapping["settlement"]

    linelist = df_planned.copy()

    # Standardize baseline columns
    linelist["LGA"] = linelist[p_lga].astype(str).str.strip()
    linelist["Ward"] = linelist[p_ward].astype(str).str.strip()
    linelist["Settlement"] = linelist[p_settlement].astype(str).str.strip()
    linelist["unique_id"] = build_unique_id(linelist, p_lga, p_ward, p_settlement)

    # Extract unique_id sets for visited sources
    gts_ids: set[str] = set()
    if df_gts is not None and not df_gts.empty and gts_mapping:
        g_lga = gts_mapping.get("lga")
        g_ward = gts_mapping.get("ward")
        g_settlement = gts_mapping.get("settlement")
        if g_lga and g_ward and g_settlement:
            gts_ids = set(build_unique_id(df_gts, g_lga, g_ward, g_settlement))

    etally_ids: set[str] = set()
    if df_etally is not None and not df_etally.empty and etally_mapping:
        e_lga = etally_mapping.get("lga")
        e_ward = etally_mapping.get("ward")
        e_settlement = etally_mapping.get("settlement")
        if e_lga and e_ward and e_settlement:
            etally_ids = set(build_unique_id(df_etally, e_lga, e_ward, e_settlement))

    mst_ids: set[str] = set()
    if df_mst is not None and not df_mst.empty and mst_mapping:
        m_lga = mst_mapping.get("lga")
        m_ward = mst_mapping.get("ward")
        m_settlement = mst_mapping.get("settlement")
        if m_lga and m_ward and m_settlement:
            mst_ids = set(build_unique_id(df_mst, m_lga, m_ward, m_settlement))

    # Calculate boolean masks
    is_gts = linelist["unique_id"].isin(gts_ids)
    is_etally = linelist["unique_id"].isin(etally_ids)
    is_mst = linelist["unique_id"].isin(mst_ids)

    # Assign binary visitation text flags
    linelist["GTS_Visited"] = is_gts.map({True: "Visited", False: "Not Visited"})
    linelist["eTally_Visited"] = is_etally.map({True: "Visited", False: "Not Visited"})
    linelist["MST_Visited"] = is_mst.map({True: "Visited", False: "Not Visited"})

    # MST + eTally Combined visitation column
    def _mst_etally_combined(row: pd.Series) -> str:
        in_mst = row["MST_Visited"] == "Visited"
        in_etally = row["eTally_Visited"] == "Visited"
        if in_mst and in_etally:
            return "Both MST & eTally"
        elif in_etally:
            return "eTally Only"
        elif in_mst:
            return "MST Only"
        return "Neither"

    linelist["MST_eTally_Combined"] = linelist.apply(_mst_etally_combined, axis=1)

    # Overall Visitation Status column
    def _overall_status(row: pd.Series) -> str:
        g = row["GTS_Visited"] == "Visited"
        e = row["eTally_Visited"] == "Visited"
        m = row["MST_Visited"] == "Visited"

        if g and e and m:
            return "Visited by All (GTS + eTally + MST)"
        elif g and e:
            return "GTS + eTally"
        elif g and m:
            return "GTS + MST"
        elif e and m:
            return "eTally + MST"
        elif g:
            return "GTS Only"
        elif e:
            return "eTally Only"
        elif m:
            return "MST Only"
        return "Not Visited"

    linelist["Overall_Visitation_Status"] = linelist.apply(_overall_status, axis=1)

    # Any Source Visited helper flag
    linelist["Any_Source_Visited"] = (is_gts | is_etally | is_mst).map(
        {True: "Visited", False: "Not Visited"}
    )

    # If GTS dataframe has extra columns, merge them into linelist by unique_id
    if df_gts is not None and not df_gts.empty and gts_mapping:
        g_lga = gts_mapping.get("lga")
        g_ward = gts_mapping.get("ward")
        g_settlement = gts_mapping.get("settlement")
        if g_lga and g_ward and g_settlement:
            gts_temp = df_gts.copy()
            gts_temp["unique_id"] = build_unique_id(gts_temp, g_lga, g_ward, g_settlement)

            # Extra columns from GTS that are not in linelist already
            gts_cols_to_add = [
                c for c in gts_temp.columns if c not in linelist.columns and c != "unique_id"
            ]
            if gts_cols_to_add:
                gts_dedup = gts_temp.drop_duplicates(subset=["unique_id"])[
                    ["unique_id"] + gts_cols_to_add
                ]
                linelist = linelist.merge(gts_dedup, on="unique_id", how="left")

    # Group by LGA to construct LGA Coverage & Linelist table
    lga_groups = linelist.groupby("LGA", dropna=False)

    lga_rows = []
    for lga_name, group in lga_groups:
        tot = len(group)
        g_cnt = (group["GTS_Visited"] == "Visited").sum()
        e_cnt = (group["eTally_Visited"] == "Visited").sum()
        m_cnt = (group["MST_Visited"] == "Visited").sum()
        me_cnt = (group["MST_eTally_Combined"] != "Neither").sum()
        all_cnt = (group["Overall_Visitation_Status"] == "Visited by All (GTS + eTally + MST)").sum()
        any_cnt = (group["Any_Source_Visited"] == "Visited").sum()
        unv_cnt = tot - any_cnt

        lga_rows.append({
            "LGA": lga_name,
            "Total Planned": tot,
            "GTS Visited": g_cnt,
            "GTS Coverage %": round((g_cnt / tot * 100), 1) if tot > 0 else 0.0,
            "eTally Visited": e_cnt,
            "eTally Coverage %": round((e_cnt / tot * 100), 1) if tot > 0 else 0.0,
            "MST Visited": m_cnt,
            "MST Coverage %": round((m_cnt / tot * 100), 1) if tot > 0 else 0.0,
            "MST + eTally Visited": me_cnt,
            "MST + eTally Coverage %": round((me_cnt / tot * 100), 1) if tot > 0 else 0.0,
            "All Sources Visited": all_cnt,
            "All Sources Coverage %": round((all_cnt / tot * 100), 1) if tot > 0 else 0.0,
            "Any Source Visited": any_cnt,
            "Any Source Coverage %": round((any_cnt / tot * 100), 1) if tot > 0 else 0.0,
            "Unvisited": unv_cnt,
            "Unvisited %": round((unv_cnt / tot * 100), 1) if tot > 0 else 0.0,
        })

    df_lga_summary = pd.DataFrame(lga_rows)

    # Compute Campaign Summary KPIs
    total_planned = len(linelist)
    gts_visited_total = (linelist["GTS_Visited"] == "Visited").sum()
    etally_visited_total = (linelist["eTally_Visited"] == "Visited").sum()
    mst_visited_total = (linelist["MST_Visited"] == "Visited").sum()
    mst_etally_total = (linelist["MST_eTally_Combined"] != "Neither").sum()
    all_sources_total = (linelist["Overall_Visitation_Status"] == "Visited by All (GTS + eTally + MST)").sum()
    any_source_total = (linelist["Any_Source_Visited"] == "Visited").sum()
    unvisited_total = total_planned - any_source_total

    summary = SettlementAnalysisSummary(
        total_planned=total_planned,
        gts_visited_count=gts_visited_total,
        gts_coverage_pct=round((gts_visited_total / total_planned * 100), 1) if total_planned > 0 else 0.0,
        etally_visited_count=etally_visited_total,
        etally_coverage_pct=round((etally_visited_total / total_planned * 100), 1) if total_planned > 0 else 0.0,
        mst_visited_count=mst_visited_total,
        mst_coverage_pct=round((mst_visited_total / total_planned * 100), 1) if total_planned > 0 else 0.0,
        mst_etally_visited_count=mst_etally_total,
        mst_etally_coverage_pct=round((mst_etally_total / total_planned * 100), 1) if total_planned > 0 else 0.0,
        all_sources_visited_count=all_sources_total,
        all_sources_coverage_pct=round((all_sources_total / total_planned * 100), 1) if total_planned > 0 else 0.0,
        any_source_visited_count=any_source_total,
        any_source_coverage_pct=round((any_source_total / total_planned * 100), 1) if total_planned > 0 else 0.0,
        unvisited_count=unvisited_total,
        unvisited_pct=round((unvisited_total / total_planned * 100), 1) if total_planned > 0 else 0.0,
        lga_count=len(df_lga_summary),
    )

    return summary, df_lga_summary, linelist


def generate_settlement_excel_report(
    summary: SettlementAnalysisSummary,
    df_lga_summary: pd.DataFrame,
    df_linelist: pd.DataFrame,
) -> bytes:
    """Generate multi-sheet Excel workbook for Settlement Analysis."""
    output = BytesIO()

    # Build Campaign Summary sheet dataframe
    summary_data = [
        {"Metric": "Total LGAs Evaluated", "Value": summary.lga_count},
        {"Metric": "Total Planned Settlements (Baseline)", "Value": summary.total_planned},
        {"Metric": "GTS Visited Settlements", "Value": f"{summary.gts_visited_count:,} ({summary.gts_coverage_pct}%)"},
        {"Metric": "eTally Visited Settlements", "Value": f"{summary.etally_visited_count:,} ({summary.etally_coverage_pct}%)"},
        {"Metric": "MST Visited Settlements", "Value": f"{summary.mst_visited_count:,} ({summary.mst_coverage_pct}%)"},
        {"Metric": "MST + eTally Visited Settlements", "Value": f"{summary.mst_etally_visited_count:,} ({summary.mst_etally_coverage_pct}%)"},
        {"Metric": "All Sources Visited (GTS + eTally + MST)", "Value": f"{summary.all_sources_visited_count:,} ({summary.all_sources_coverage_pct}%)"},
        {"Metric": "Any Source Visited", "Value": f"{summary.any_source_visited_count:,} ({summary.any_source_coverage_pct}%)"},
        {"Metric": "Unvisited Settlements", "Value": f"{summary.unvisited_count:,} ({summary.unvisited_pct}%)"},
    ]
    df_summary_sheet = pd.DataFrame(summary_data)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_summary_sheet.to_excel(writer, sheet_name="Campaign Summary", index=False)
        df_lga_summary.to_excel(writer, sheet_name="LGA Coverage & Summary", index=False)
        df_linelist.to_excel(writer, sheet_name="Settlement Linelist", index=False)

    return output.getvalue()

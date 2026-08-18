"""Pure data processing engine for Ward Coverage Analysis.

All public functions are free of Streamlit imports so they can be unit-tested
without a running Streamlit server.

Ward Coverage Analysis accepts ward-level data directly — no settlement-to-ward
aggregation is needed.  Three ward-level datasets (Vaccination Coverage required,
Household Coverage and Visitation optional) are joined on a composite LGA + Ward
key to produce a single ward master table.

Reuses shared constructs from the Coverage Analysis module:
- CoverageThreshold, DEFAULT_THRESHOLDS, apply_thresholds
- _coerce_numeric (percentage coercion)
- _apply_excel_formatting (Excel styling)
- Operational issue detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import re
from typing import TypeAlias

import pandas as pd

# Reuse shared constructs from Coverage Analysis to avoid duplication.
from campaign_analytics.modules.coverage_analysis.processor import (
    COL_HOUSEHOLD,
    COL_ISSUE_TYPE,
    COL_LGA,
    COL_VACCINATION,
    COL_VISITATION,
    COL_WARD,
    CoverageThreshold,
    DEFAULT_THRESHOLDS,
    ISSUE_DESCRIPTIONS,
    ISSUE_LABELS,
    ISSUE_TYPES,
    STATUS_HOUSEHOLD,
    STATUS_VACCINATION,
    STATUS_VISITATION,
    _apply_excel_formatting,
    _coerce_numeric,
    _normalise_name,
    apply_thresholds,
    detect_operational_issues,
    normalize_text_series,
)

MappingDict: TypeAlias = dict[str, str | None]

# Canonical field identifiers used by the column mapper.
WARD_VACCINATION_FIELDS = ("lga", "ward", "vaccination_coverage")
WARD_HOUSEHOLD_FIELDS = ("lga", "ward", "household_coverage")
WARD_VISITATION_FIELDS = ("lga", "ward", "visitation_coverage")
WARD_VISITATION_REQUIRED_FIELDS = ("lga", "ward")

# Output column order for the ward master table.
WARD_MASTER_COLUMNS = [
    COL_LGA, COL_WARD,
    COL_VISITATION, COL_VACCINATION, COL_HOUSEHOLD,
]


# ── Data contracts ────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ValidationReport:
    """Validation outcome for Ward Coverage Analysis inputs."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return whether required data is valid for processing."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class WardCoverageAnalysisSummary:
    """Campaign-level KPIs for Ward Coverage Analysis."""

    total_wards: int
    total_lgas: int
    avg_visitation_pct: float
    avg_vaccination_pct: float
    avg_household_pct: float


# ── Column suggestion helpers ─────────────────────────────────────────────────

def _suggest_mapping(
    columns: list[str], aliases: dict[str, tuple[str, ...]]
) -> MappingDict:
    """Auto-suggest column mappings from a dictionary of normalised aliases."""
    normalised = {_normalise_name(col): col for col in columns}
    return {
        field_key: next(
            (normalised[name] for name in names if name in normalised), None
        )
        for field_key, names in aliases.items()
    }


def suggest_ward_vaccination_mapping(columns: list[str]) -> MappingDict:
    """Suggest column mappings for ward-level Vaccination Coverage dataset."""
    return _suggest_mapping(
        columns,
        {
            "lga": ("lga", "localgovernmentarea", "district", "lganame"),
            "ward": ("ward", "wardname", "ward_name", "subdistrict"),
            "vaccination_coverage": (
                "vaccinationcoverage", "coveragepct", "coverage",
                "vaccinationcoveragepct", "vacccoverage",
                "vaccination_coverage", "coveragepercent",
                "vaccination", "avgvaccinationcoverage",
            ),
        },
    )


def suggest_ward_household_mapping(columns: list[str]) -> MappingDict:
    """Suggest column mappings for ward-level Household Coverage dataset."""
    return _suggest_mapping(
        columns,
        {
            "lga": ("lga", "localgovernmentarea", "district", "lganame"),
            "ward": ("ward", "wardname", "ward_name", "subdistrict"),
            "household_coverage": (
                "householdcoverage", "householdcoveragepct",
                "hhcoverage", "hhcoveragepct", "household_coverage",
                "householdcoveragepercent", "household",
                "avghouseholdcoverage",
            ),
        },
    )


def suggest_ward_visitation_mapping(columns: list[str]) -> MappingDict:
    """Suggest column mappings for ward-level Visitation dataset."""
    return _suggest_mapping(
        columns,
        {
            "lga": ("lga", "localgovernmentarea", "district", "lganame"),
            "ward": ("ward", "wardname", "ward_name", "subdistrict"),
            "visitation_coverage": (
                "visitation", "visitationpct", "visitationcoverage",
                "visitation_coverage", "visitationpercent",
                "percentvisitation", "pctvisitation",
                "vaccinationcoverage", "coveragepct", "coverage",
            ),
        },
    )


# ── Text normalisation ────────────────────────────────────────────────────────

def build_ward_unique_id(
    df: pd.DataFrame, lga_col: str, ward_col: str
) -> pd.Series:
    """Create a composite unique identifier (LGA_Ward) for joining."""
    lga = normalize_text_series(df[lga_col])
    ward = normalize_text_series(df[ward_col])
    return lga + "_" + ward


# ── Validation ────────────────────────────────────────────────────────────────

def validate_ward_inputs(
    df_vaccination: pd.DataFrame | None,
    vaccination_mapping: MappingDict,
    df_household: pd.DataFrame | None = None,
    household_mapping: MappingDict | None = None,
    df_visitation: pd.DataFrame | None = None,
    visitation_mapping: MappingDict | None = None,
) -> ValidationReport:
    """Validate uploaded ward-level dataframes and field mappings."""
    report = ValidationReport()

    # Vaccination Coverage is the baseline — required.
    if df_vaccination is None or df_vaccination.empty:
        report.errors.append(
            "Ward-level Vaccination Coverage dataset is required as the baseline ward list."
        )
        return report

    # Validate vaccination mapping (all three fields required).
    _validate_required_mapping(
        df_vaccination, vaccination_mapping, WARD_VACCINATION_FIELDS,
        "Vaccination Coverage", report,
    )

    # Validate household mapping if uploaded.
    if df_household is not None and not df_household.empty and household_mapping:
        _validate_required_mapping(
            df_household, household_mapping, WARD_HOUSEHOLD_FIELDS,
            "Household Coverage", report,
        )
        hh_col = household_mapping.get("household_coverage")
        if hh_col and hh_col in df_household.columns:
            _validate_percentage_column(
                df_household, hh_col, "Household Coverage %", report,
            )

    # Validate visitation mapping if uploaded.
    if df_visitation is not None and not df_visitation.empty and visitation_mapping:
        _validate_required_mapping(
            df_visitation, visitation_mapping, WARD_VISITATION_REQUIRED_FIELDS,
            "Visitation", report,
        )
        vis_col = visitation_mapping.get("visitation_coverage")
        if vis_col and vis_col in df_visitation.columns:
            _validate_percentage_column(
                df_visitation, vis_col, "Visitation %", report,
            )

    # Validate vaccination coverage numeric column.
    vacc_col = vaccination_mapping.get("vaccination_coverage")
    if vacc_col and vacc_col in df_vaccination.columns:
        _validate_percentage_column(
            df_vaccination, vacc_col, "Vaccination Coverage %", report,
        )

    # Advisory warnings when optional datasets are missing.
    if df_household is None or df_household.empty:
        report.warnings.append(
            "No Household Coverage dataset uploaded. "
            "Household Coverage % will show as 'N/A' in the ward table."
        )
    if df_visitation is None or df_visitation.empty:
        report.warnings.append(
            "No Visitation dataset uploaded. "
            "% Visitation will show as 'N/A' in the ward table."
        )

    return report


def _validate_required_mapping(
    df: pd.DataFrame,
    mapping: MappingDict,
    fields: tuple[str, ...],
    dataset_name: str,
    report: ValidationReport,
) -> None:
    """Check that every required field is mapped and the column exists."""
    for field_key in fields:
        mapped_col = mapping.get(field_key)
        if not mapped_col:
            report.errors.append(
                f"{dataset_name}: please map the required field "
                f"'{field_key.replace('_', ' ').title()}'."
            )
        elif mapped_col not in df.columns:
            report.errors.append(
                f"{dataset_name}: mapped column '{mapped_col}' "
                f"for '{field_key.replace('_', ' ').title()}' was not found in the file."
            )


def _validate_percentage_column(
    df: pd.DataFrame,
    column: str,
    label: str,
    report: ValidationReport,
) -> None:
    """Check a percentage column for blanks and out-of-range values."""
    numeric = _coerce_numeric(df[column])
    invalid_count = int(numeric.isna().sum())
    if invalid_count:
        report.warnings.append(
            f"{label}: {invalid_count:,} blank or non-numeric value(s) "
            "will be treated as N/A."
        )
    negative = int((numeric.dropna() < 0).sum())
    if negative:
        report.warnings.append(
            f"{label}: {negative:,} value(s) below 0% found."
        )
    over_100 = int((numeric.dropna() > 100).sum())
    if over_100:
        report.warnings.append(
            f"{label}: {over_100:,} value(s) above 100% found."
        )


# ── Processing ────────────────────────────────────────────────────────────────

def build_ward_master(
    df_vaccination: pd.DataFrame,
    vaccination_mapping: MappingDict,
    df_household: pd.DataFrame | None = None,
    household_mapping: MappingDict | None = None,
    df_visitation: pd.DataFrame | None = None,
    visitation_mapping: MappingDict | None = None,
) -> tuple[WardCoverageAnalysisSummary, pd.DataFrame]:
    """Build the ward-level master table from ward-level input datasets.

    The Vaccination Coverage dataset provides the baseline ward roster.
    Household Coverage and Visitation are left-joined onto it via
    a composite key (LGA_WARD, uppercased and stripped).

    Returns:
        (summary_kpis, ward_master_dataframe)
    """
    v_lga = vaccination_mapping["lga"]
    v_ward = vaccination_mapping["ward"]
    v_coverage = vaccination_mapping["vaccination_coverage"]

    # Build baseline from vaccination dataset.
    master = pd.DataFrame({
        COL_LGA: df_vaccination[v_lga].astype(str).str.strip(),
        COL_WARD: df_vaccination[v_ward].astype(str).str.strip(),
        COL_VACCINATION: _coerce_numeric(df_vaccination[v_coverage]),
    })
    master["unique_id"] = build_ward_unique_id(
        df_vaccination, v_lga, v_ward
    )

    # Deduplicate on ward key — take the first occurrence.
    master = master.drop_duplicates(subset=["unique_id"], keep="first")

    # ── Join Household Coverage ───────────────────────────────────────────
    if (
        df_household is not None
        and not df_household.empty
        and household_mapping
        and all(household_mapping.get(f) for f in WARD_HOUSEHOLD_FIELDS)
    ):
        h_lga = household_mapping["lga"]
        h_ward = household_mapping["ward"]
        h_coverage = household_mapping["household_coverage"]

        hh = pd.DataFrame({
            "unique_id": build_ward_unique_id(
                df_household, h_lga, h_ward
            ),
            COL_HOUSEHOLD: _coerce_numeric(df_household[h_coverage]),
        })
        # Deduplicate on key — take the first occurrence.
        hh = hh.drop_duplicates(subset=["unique_id"], keep="first")
        master = master.merge(hh, on="unique_id", how="left")
    else:
        master[COL_HOUSEHOLD] = pd.NA

    # ── Join Visitation ───────────────────────────────────────────────────
    if (
        df_visitation is not None
        and not df_visitation.empty
        and visitation_mapping
        and all(visitation_mapping.get(f) for f in WARD_VISITATION_REQUIRED_FIELDS)
    ):
        vis_lga = visitation_mapping["lga"]
        vis_ward = visitation_mapping["ward"]

        vis_cov_col = visitation_mapping.get("visitation_coverage")

        if vis_cov_col and vis_cov_col in df_visitation.columns:
            vis_df = pd.DataFrame({
                "unique_id": build_ward_unique_id(
                    df_visitation, vis_lga, vis_ward
                ),
                COL_VISITATION: _coerce_numeric(df_visitation[vis_cov_col]),
            }).drop_duplicates(subset=["unique_id"], keep="first")

            master = master.merge(vis_df, on="unique_id", how="left")
        else:
            # Visitation uploaded but no coverage column — mark present wards as 100%.
            vis_ids = set(build_ward_unique_id(df_visitation, vis_lga, vis_ward))
            master[COL_VISITATION] = master["unique_id"].isin(vis_ids).map(
                {True: 100.0, False: 0.0}
            )
    else:
        master[COL_VISITATION] = pd.NA

    # Drop internal join key.
    master = master.drop(columns=["unique_id"])

    # Round percentage columns to integer.
    for col in [COL_VACCINATION, COL_HOUSEHOLD, COL_VISITATION]:
        if col in master.columns:
            master[col] = pd.to_numeric(master[col], errors="coerce").round(0)

    # Reorder columns to match the spec.
    available_cols = [c for c in WARD_MASTER_COLUMNS if c in master.columns]
    master = master[available_cols].reset_index(drop=True)

    # ── Summary KPIs ─────────────────────────────────────────────────────
    total_wards = len(master)
    total_lgas = master[COL_LGA].nunique()

    avg_vis = round(master[COL_VISITATION].dropna().mean(), 0) if master[COL_VISITATION].notna().any() else 0.0
    avg_vacc = round(master[COL_VACCINATION].dropna().mean(), 0) if master[COL_VACCINATION].notna().any() else 0.0
    avg_hh = round(master[COL_HOUSEHOLD].dropna().mean(), 0) if master[COL_HOUSEHOLD].notna().any() else 0.0

    summary = WardCoverageAnalysisSummary(
        total_wards=total_wards,
        total_lgas=total_lgas,
        avg_visitation_pct=avg_vis,
        avg_vaccination_pct=avg_vacc,
        avg_household_pct=avg_hh,
    )

    return summary, master


# ── Excel export ──────────────────────────────────────────────────────────────

def generate_ward_coverage_excel_report(
    summary: WardCoverageAnalysisSummary | None,
    df_ward: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold] | None = None,
    df_issues: pd.DataFrame | None = None,
) -> bytes:
    """Generate multi-sheet Executive Summary Excel workbook for Ward Coverage Analysis.

    Sheets:
    1. Executive Summary — high-level KPIs and campaign overview
    2. Ward Coverage — ward master table with RAG styling
    3. Operational Issues — detected misalignment issues (if any) with RAG styling
    4. Threshold Settings — active threshold configuration
    """
    output = BytesIO()

    if summary is not None:
        summary_data = [
            {"Campaign Metric": "Total LGAs Analysed", "Value": summary.total_lgas},
            {"Campaign Metric": "Total Wards Analysed", "Value": summary.total_wards},
            {"Campaign Metric": "Avg. Visitation %", "Value": f"{int(round(summary.avg_visitation_pct))}%"},
            {"Campaign Metric": "Avg. Vaccination Coverage %", "Value": f"{int(round(summary.avg_vaccination_pct))}%"},
            {"Campaign Metric": "Avg. Household Coverage %", "Value": f"{int(round(summary.avg_household_pct))}%"},
        ]
        if df_issues is not None and not df_issues.empty:
            summary_data.append({"Campaign Metric": "Wards with Operational Issues", "Value": df_issues[COL_WARD].nunique()})
    else:
        summary_data = [{"Campaign Metric": "Status", "Value": "No Summary Available"}]

    df_summary_sheet = pd.DataFrame(summary_data)

    # Build threshold documentation sheet.
    threshold_rows: list[dict] = []
    active_thresholds = thresholds or DEFAULT_THRESHOLDS
    for indicator, threshold in active_thresholds.items():
        threshold_rows.append({
            "Indicator": indicator,
            "🔴 Red": f"Below {threshold.yellow_min}%",
            "🟡 Yellow": f"{threshold.yellow_min}% - {threshold.green_min - 1}%",
            "🟢 Green": f"{threshold.green_min}% and above",
        })
    df_thresholds = pd.DataFrame(threshold_rows)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_summary_sheet.to_excel(writer, sheet_name="Executive Summary", index=False)
        df_ward.to_excel(writer, sheet_name="Ward Coverage", index=False)
        if df_issues is not None and not df_issues.empty:
            df_issues.to_excel(writer, sheet_name="Operational Issues", index=False)
        df_thresholds.to_excel(writer, sheet_name="Threshold Settings", index=False)

        wb = writer.book
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            _apply_excel_formatting(
                ws,
                sheet_name,
                thresholds=active_thresholds,
            )

    return output.getvalue()

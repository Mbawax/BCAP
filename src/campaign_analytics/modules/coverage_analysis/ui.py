"""Streamlit UI workflow for Coverage Analysis.

This module combines settlement-level Vaccination Coverage, Household Coverage,
and Settlement Visitation data into a master table, then provides both
settlement-level and ward-level analysis views.

Complete Workflow
-----------------
Data -> Settlement Master -> Ward Aggregation -> Thresholds -> RAG Flags
     -> Operational Issues -> Settlement Drill-down -> Downloads
"""

from hashlib import sha256

import pandas as pd
import streamlit as st

from campaign_analytics.components.column_mapper import render_column_mapper
from campaign_analytics.components.data_io import read_tabular_upload, source_preview
from campaign_analytics.components.notifications import validation_messages
from campaign_analytics.components.tables import data_table
from campaign_analytics.components.upload import upload_data_file
from campaign_analytics.modules.coverage_analysis.processor import (
    COL_HOUSEHOLD,
    COL_ISSUE_TYPE,
    COL_LGA,
    COL_VACCINATION,
    COL_VISITATION,
    COL_WARD,
    COL_SETTLEMENT,
    CoverageAnalysisSummary,
    CoverageThreshold,
    DEFAULT_THRESHOLDS,
    HOUSEHOLD_FIELDS,
    ISSUE_DESCRIPTIONS,
    ISSUE_LABELS,
    STATUS_HOUSEHOLD,
    STATUS_VACCINATION,
    STATUS_VISITATION,
    VACCINATION_FIELDS,
    VISITATION_FIELDS,
    VISITATION_REQUIRED_FIELDS,
    _apply_excel_formatting,
    apply_thresholds,
    build_settlement_master,
    build_ward_summary,
    detect_operational_issues,
    generate_coverage_excel_report,
    suggest_household_mapping,
    suggest_vaccination_mapping,
    suggest_visitation_mapping,
    validate_inputs,
)
from campaign_analytics.ui.components import kpi_card, page_header

MODULE_KEY = "coverage_analysis"

# Mapping from indicator column to its status column (for display ordering).
_INDICATOR_COLS = [COL_VISITATION, COL_VACCINATION, COL_HOUSEHOLD]
_STATUS_COLS = [STATUS_VISITATION, STATUS_VACCINATION, STATUS_HOUSEHOLD]

# Colours used for conditional formatting — accessible and high contrast.
_STATUS_COLOURS = {
    "Red": "background-color: #FECACA; color: #991B1B",
    "Yellow": "background-color: #FEF08A; color: #854D0E",
    "Green": "background-color: #BBF7D0; color: #166534",
    "N/A": "background-color: #F3F4F6; color: #6B7280",
}


def render_coverage_analysis_module() -> None:
    """Render the complete Coverage Analysis workflow."""
    _initialise_state()

    page_header(
        "Coverage Analysis",
        "Combine settlement-level campaign indicators to produce both "
        "settlement-level and ward-level coverage analysis.",
        "Campaign module",
    )

    df_vaccination, df_household, df_visitation = _render_uploads()
    if df_vaccination is None:
        st.info(
            "Please upload the **Vaccination Coverage** dataset to proceed. "
            "This dataset provides the baseline settlement roster."
        )
        return

    vacc_mapping, hh_mapping, vis_mapping = _render_mappers(
        df_vaccination, df_household, df_visitation
    )

    _clear_stale_results(vacc_mapping, hh_mapping, vis_mapping)

    report = validate_inputs(
        df_vaccination, vacc_mapping,
        df_household, hh_mapping,
        df_visitation, vis_mapping,
    )

    _render_validation(report)

    if st.button(
        "Run Coverage Analysis",
        type="primary",
        disabled=not report.is_valid,
        key=f"{MODULE_KEY}_run_button",
    ):
        summary, df_master = build_settlement_master(
            df_vaccination=df_vaccination,
            vaccination_mapping=vacc_mapping,
            df_household=df_household,
            household_mapping=hh_mapping,
            df_visitation=df_visitation,
            visitation_mapping=vis_mapping,
        )
        df_ward = build_ward_summary(df_master)
        st.session_state[f"{MODULE_KEY}_results"] = {
            "summary": summary,
            "settlement": df_master,
            "ward": df_ward,
            "fingerprint": _compute_fingerprint(
                vacc_mapping, hh_mapping, vis_mapping
            ),
        }

    results = st.session_state.get(f"{MODULE_KEY}_results")
    if results:
        _render_results(
            results["summary"],
            results["settlement"],
            results["ward"],
        )


# ── Session state ─────────────────────────────────────────────────────────────

def _initialise_state() -> None:
    """Initialize session state variables for coverage analysis."""
    defaults = {
        f"{MODULE_KEY}_vacc_file": None,
        f"{MODULE_KEY}_hh_file": None,
        f"{MODULE_KEY}_vis_file": None,
        f"{MODULE_KEY}_results": None,
        f"{MODULE_KEY}_thresholds": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ── Uploads ───────────────────────────────────────────────────────────────────

def _render_uploads() -> tuple[
    pd.DataFrame | None,
    pd.DataFrame | None,
    pd.DataFrame | None,
]:
    """Render upload controls for the three input datasets."""
    st.subheader("1. File Uploads")

    c1, c2, c3 = st.columns(3)
    with c1:
        vacc_upload = upload_data_file(
            "Vaccination Coverage *",
            key=f"{MODULE_KEY}_vacc_upload",
            help_text=(
                "Upload the Vaccination Coverage dataset with LGA, Ward, "
                "Settlement, and Vaccination Coverage % columns."
            ),
        )
    with c2:
        hh_upload = upload_data_file(
            "Household Coverage (Optional)",
            key=f"{MODULE_KEY}_hh_upload",
            help_text=(
                "Upload the Household Coverage dataset with LGA, Ward, "
                "Settlement, and Household Coverage % columns."
            ),
        )
    with c3:
        vis_upload = upload_data_file(
            "Settlement Visitation (Optional)",
            key=f"{MODULE_KEY}_vis_upload",
            help_text=(
                "Upload the Settlement Visitation submission data with "
                "LGA, Ward, and Settlement columns."
            ),
        )

    df_vaccination = _load_dataframe(vacc_upload, "vacc")
    df_household = _load_dataframe(hh_upload, "hh")
    df_visitation = _load_dataframe(vis_upload, "vis")

    with st.expander("Uploaded Datasets Preview"):
        if df_vaccination is not None and vacc_upload:
            source_preview(df_vaccination, vacc_upload.name)
        if df_household is not None and hh_upload:
            source_preview(df_household, hh_upload.name)
        if df_visitation is not None and vis_upload:
            source_preview(df_visitation, vis_upload.name)

    return df_vaccination, df_household, df_visitation


def _load_dataframe(file_obj, prefix: str) -> pd.DataFrame | None:
    """Helper to read and cache uploaded dataset bytes."""
    if file_obj is None:
        st.session_state[f"{MODULE_KEY}_{prefix}_file"] = None
        return None

    state_key = f"{MODULE_KEY}_{prefix}_file"
    current_signature = (file_obj.name, file_obj.size)
    if st.session_state.get(state_key) != current_signature:
        st.session_state[state_key] = current_signature

    return read_tabular_upload(file_obj.getvalue(), file_obj.name)


# ── Column mappers ────────────────────────────────────────────────────────────

def _render_mappers(
    df_vaccination: pd.DataFrame,
    df_household: pd.DataFrame | None,
    df_visitation: pd.DataFrame | None,
) -> tuple[dict, dict, dict]:
    """Render column mapping UI sections for all uploaded datasets."""
    st.subheader("2. Column Mappings")
    st.caption(
        "Map LGA, Ward, Settlement, and coverage columns for accurate analysis."
    )

    # Vaccination Coverage (Required).
    st.markdown("##### 💉 Vaccination Coverage Mappings")
    vacc_suggestions = suggest_vaccination_mapping(list(df_vaccination.columns))
    vacc_mapping = render_column_mapper(
        fields=list(VACCINATION_FIELDS),
        required_fields=set(VACCINATION_FIELDS),
        source_columns=list(df_vaccination.columns),
        suggestions=vacc_suggestions,
        key_prefix=f"{MODULE_KEY}_vacc",
    )

    # Household Coverage.
    hh_mapping: dict = {}
    if df_household is not None and not df_household.empty:
        st.markdown("##### 🏠 Household Coverage Mappings")
        hh_suggestions = suggest_household_mapping(list(df_household.columns))
        hh_mapping = render_column_mapper(
            fields=list(HOUSEHOLD_FIELDS),
            required_fields=set(HOUSEHOLD_FIELDS),
            source_columns=list(df_household.columns),
            suggestions=hh_suggestions,
            key_prefix=f"{MODULE_KEY}_hh",
        )

    # Settlement Visitation.
    vis_mapping: dict = {}
    if df_visitation is not None and not df_visitation.empty:
        st.markdown("##### 📍 Settlement Visitation Mappings")
        vis_suggestions = suggest_visitation_mapping(list(df_visitation.columns))
        vis_mapping = render_column_mapper(
            fields=list(VISITATION_FIELDS),
            required_fields=set(VISITATION_REQUIRED_FIELDS),
            source_columns=list(df_visitation.columns),
            suggestions=vis_suggestions,
            key_prefix=f"{MODULE_KEY}_vis",
        )

    return vacc_mapping, hh_mapping, vis_mapping


# ── Validation ────────────────────────────────────────────────────────────────

def _render_validation(report) -> None:
    """Render error and warning notifications from validation report."""
    validation_messages(report.errors, report.warnings)


# ── Coverage Threshold Configuration ──────────────────────────────────────────

def _get_active_thresholds() -> dict[str, CoverageThreshold]:
    """Return the current user-configured thresholds or the defaults."""
    custom = st.session_state.get(f"{MODULE_KEY}_thresholds")
    if custom is not None:
        return custom
    return dict(DEFAULT_THRESHOLDS)


def _render_threshold_config() -> dict[str, CoverageThreshold]:
    """Render the threshold configuration UI and return current thresholds."""
    st.subheader("3. Coverage Thresholds")
    st.caption(
        "Configure Red / Yellow / Green classification boundaries for each "
        "indicator.  These are applied as a presentation layer — the underlying "
        "percentages are not modified."
    )

    current = _get_active_thresholds()

    with st.expander("🎨 Configure Coverage Thresholds", expanded=False):
        _render_active_thresholds_summary(current)

        st.markdown("---")
        st.markdown("##### Adjust Thresholds")

        indicators = [
            (COL_VISITATION, "🚶 % Visitation"),
            (COL_VACCINATION, "💉 % Vaccination"),
            (COL_HOUSEHOLD, "🏠 % Household Coverage"),
        ]

        updated: dict[str, CoverageThreshold] = {}

        for indicator_col, label in indicators:
            threshold = current[indicator_col]
            st.markdown(f"**{label}**")
            c1, c2 = st.columns(2)
            with c1:
                yellow_min = st.number_input(
                    f"Red below (Yellow starts at):",
                    min_value=0.0,
                    max_value=100.0,
                    value=threshold.yellow_min,
                    step=1.0,
                    key=f"{MODULE_KEY}_thresh_{indicator_col}_yellow",
                    help=f"Values below this are Red for {label}.",
                )
            with c2:
                green_min = st.number_input(
                    f"Yellow below (Green starts at):",
                    min_value=0.0,
                    max_value=100.0,
                    value=threshold.green_min,
                    step=1.0,
                    key=f"{MODULE_KEY}_thresh_{indicator_col}_green",
                    help=f"Values at or above this are Green for {label}.",
                )

            # Validate that yellow_min <= green_min.
            if yellow_min > green_min:
                st.warning(
                    f"{label}: Red boundary ({yellow_min}%) must be ≤ "
                    f"Green boundary ({green_min}%).  Using Green boundary "
                    "as the Red boundary.",
                    icon="⚠️",
                )
                yellow_min = green_min

            updated[indicator_col] = CoverageThreshold(
                yellow_min=yellow_min, green_min=green_min
            )

        # Apply / Reset buttons.
        col_apply, col_reset = st.columns(2)
        with col_apply:
            if st.button(
                "Apply Thresholds",
                type="primary",
                key=f"{MODULE_KEY}_apply_thresholds",
            ):
                st.session_state[f"{MODULE_KEY}_thresholds"] = updated
                st.success("Thresholds updated successfully.", icon="✅")
        with col_reset:
            if st.button(
                "Reset to Defaults",
                key=f"{MODULE_KEY}_reset_thresholds",
            ):
                st.session_state[f"{MODULE_KEY}_thresholds"] = None
                st.info(
                    "Thresholds reset to platform defaults "
                    "(Red < 49%, Yellow 49-69%, Green ≥ 70%).",
                    icon="🔄",
                )

    return _get_active_thresholds()


def _render_active_thresholds_summary(
    thresholds: dict[str, CoverageThreshold],
) -> None:
    """Display the currently active thresholds in a clear summary table."""
    st.markdown("##### Active Thresholds")
    rows = []
    labels = {
        COL_VISITATION: "% Visitation",
        COL_VACCINATION: "% Vaccination",
        COL_HOUSEHOLD: "% Household Coverage",
    }
    for indicator_col, label in labels.items():
        threshold = thresholds[indicator_col]
        rows.append({
            "Indicator": label,
            "🔴 Red": f"Below {threshold.yellow_min}%",
            "🟡 Yellow": f"{threshold.yellow_min}% – {threshold.green_min - 0.1}%",
            "🟢 Green": f"{threshold.green_min}% and above",
        })
    data_table(pd.DataFrame(rows))


# ── Fingerprinting / stale result detection ───────────────────────────────────

def _clear_stale_results(v_map, h_map, vis_map) -> None:
    """Clear session state results if mapping input fingerprint changes."""
    fingerprint = _compute_fingerprint(v_map, h_map, vis_map)
    results = st.session_state.get(f"{MODULE_KEY}_results")
    if results and results.get("fingerprint") != fingerprint:
        st.session_state[f"{MODULE_KEY}_results"] = None


def _compute_fingerprint(v_map, h_map, vis_map) -> str:
    """Compute string hash of current user column selections."""
    raw = f"{v_map}|{h_map}|{vis_map}"
    return sha256(raw.encode("utf-8")).hexdigest()


# ── Conditional indicator formatting ──────────────────────────────────────────

def format_pct(val) -> str:
    """Format numeric coverage value as a clean percentage string (e.g. '60%', '60.5%')."""
    if pd.isna(val) or val is None:
        return "N/A"
    try:
        num = float(val)
        if num == int(num):
            return f"{int(num)}%"
        return f"{num:.1f}%"
    except (ValueError, TypeError):
        return str(val)


def _style_dataframe(
    df: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
) -> object:
    """Apply background colors to percentage indicator columns based on thresholds and 100 rule.

    - 100% or above -> Green (#BBF7D0 background, #166534 text)
    - Below 100% -> Classified against user thresholds (Red / Yellow / Green / N/A)
    - Status columns remain untouched with their existing emoji badges.
    """
    def _color_indicator_cell(val, indicator_col: str) -> str:
        if pd.isna(val) or val is None:
            return "background-color: #F3F4F6; color: #6B7280"
        try:
            num_val = float(val)
        except (ValueError, TypeError):
            return ""

        # 100% or above is Green
        if num_val >= 100.0:
            return "background-color: #BBF7D0; color: #166534"

        # Below 100% is colored based on user threshold
        t = thresholds.get(indicator_col)
        if not t:
            return ""

        status = t.classify(num_val)
        if "Red" in status:
            return "background-color: #FECACA; color: #991B1B"
        elif "Yellow" in status:
            return "background-color: #FEF08A; color: #854D0E"
        elif "Green" in status:
            return "background-color: #BBF7D0; color: #166534"
        return "background-color: #F3F4F6; color: #6B7280"

    styler = df.style

    pct_format = {}
    for col in _INDICATOR_COLS:
        if col in df.columns:
            styler = styler.map(
                lambda v, c=col: _color_indicator_cell(v, c),
                subset=[col],
            )
            pct_format[col] = format_pct

    if pct_format:
        styler = styler.format(pct_format, na_rep="N/A")

    return styler


def _render_styled_table(
    df: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
    height: int | None = None,
) -> None:
    """Render a DataFrame with conditional indicator background colors."""
    styled = _style_dataframe(df, thresholds)
    data_table(styled, height=height)


# ── Results ───────────────────────────────────────────────────────────────────

def _render_results(
    summary: CoverageAnalysisSummary,
    df_settlement: pd.DataFrame,
    df_ward: pd.DataFrame,
) -> None:
    """Render threshold config, then tabs for results."""
    st.markdown("---")

    # Threshold configuration — always visible when results exist.
    thresholds = _render_threshold_config()

    # Apply thresholds to both tables (presentation layer only).
    df_settlement_display = apply_thresholds(df_settlement, thresholds)
    df_ward_display = apply_thresholds(df_ward, thresholds)

    # Detect operational issues from ward-level data.
    df_issues = detect_operational_issues(df_ward, thresholds)

    st.subheader("4. Coverage Analysis Results")

    tab_summary, tab_settlement, tab_ward, tab_issues, tab_downloads = st.tabs([
        "📊 Summary",
        "📋 Settlement Level",
        "🗺️ Ward Level",
        "⚠️ Operational Issues",
        "📥 Downloads & Export",
    ])

    with tab_summary:
        _render_summary_tab(summary, df_settlement, df_ward, df_issues)

    with tab_settlement:
        _render_settlement_tab(df_settlement_display, thresholds)

    with tab_ward:
        _render_ward_tab(df_ward_display, thresholds)

    with tab_issues:
        _render_issues_tab(
            df_issues, df_settlement_display, thresholds
        )

    with tab_downloads:
        _render_downloads_tab(
            summary, df_settlement_display, df_ward_display,
            thresholds, df_issues,
        )


def _render_summary_tab(
    summary: CoverageAnalysisSummary,
    df_settlement: pd.DataFrame,
    df_ward: pd.DataFrame,
    df_issues: pd.DataFrame,
) -> None:
    """Render KPI cards."""
    k1, k2, k3 = st.columns(3)
    with k1:
        kpi_card(
            "Total Settlements",
            f"{summary.total_settlements:,}",
            f"{summary.total_lgas} LGAs · {summary.total_wards} Wards",
        )
    with k2:
        kpi_card(
            "Settlement Visitation",
            f"{summary.visited_settlements:,}",
            f"{summary.visitation_pct}% Visited",
        )
    with k3:
        kpi_card(
            "Unvisited Settlements",
            f"{summary.total_settlements - summary.visited_settlements:,}",
            f"{round(100 - summary.visitation_pct, 1)}% Unvisited",
        )

    k4, k5, k6 = st.columns(3)
    with k4:
        kpi_card(
            "Avg. Vaccination Coverage",
            f"{summary.avg_vaccination_pct}%",
            "Mean across settlements",
        )
    with k5:
        kpi_card(
            "Avg. Household Coverage",
            f"{summary.avg_household_pct}%",
            "Mean across settlements",
        )
    with k6:
        # Count unique wards with at least one issue.
        wards_with_issues = (
            df_issues[COL_WARD].nunique() if not df_issues.empty else 0
        )
        kpi_card(
            "Wards with Issues",
            f"{wards_with_issues}",
            f"of {summary.total_wards} total wards",
        )


def _render_settlement_tab(
    df_settlement: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
) -> None:
    """Render interactive settlement-level master table with conditional formatting."""
    st.markdown("#### Settlement-Level Coverage Master Table")

    # Filter controls.
    col_lga, col_ward, col_status = st.columns(3)
    with col_lga:
        lgas = ["All"] + sorted(
            df_settlement[COL_LGA].dropna().unique().tolist()
        )
        selected_lga = st.selectbox(
            "Filter by LGA:",
            lgas,
            key=f"{MODULE_KEY}_settlement_lga_filter",
        )
    with col_ward:
        ward_options = ["All"]
        if selected_lga != "All":
            ward_options += sorted(
                df_settlement.loc[
                    df_settlement[COL_LGA] == selected_lga, "Ward"
                ].dropna().unique().tolist()
            )
        else:
            ward_options += sorted(
                df_settlement["Ward"].dropna().unique().tolist()
            )
        selected_ward = st.selectbox(
            "Filter by Ward:",
            ward_options,
            key=f"{MODULE_KEY}_settlement_ward_filter",
        )
    with col_status:
        status_options = ["All", "Red", "Yellow", "Green", "N/A"]
        selected_status = st.selectbox(
            "Filter by Status (any indicator):",
            status_options,
            key=f"{MODULE_KEY}_settlement_status_filter",
        )

    filtered = df_settlement.copy()
    if selected_lga != "All":
        filtered = filtered[filtered[COL_LGA] == selected_lga]
    if selected_ward != "All":
        filtered = filtered[filtered["Ward"] == selected_ward]
    if selected_status != "All":
        status_cols = [c for c in _STATUS_COLS if c in filtered.columns]
        if status_cols:
            mask = filtered[status_cols].apply(
                lambda col: col.astype(str).str.contains(selected_status, case=False, na=False)
            ).any(axis=1)
            filtered = filtered[mask]

    st.caption(
        f"Displaying {len(filtered):,} of {len(df_settlement):,} settlements"
    )
    _render_styled_table(filtered, thresholds)


def _render_ward_tab(
    df_ward: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
) -> None:
    """Render ward-level aggregated table with conditional formatting."""
    st.markdown("#### Ward-Level Coverage Summary")
    st.info(
        "**Aggregation method:** % Visitation = (visited / total settlements) × 100. "
        "% Vaccination and % Household Coverage = mean of settlement-level values. "
        "Each settlement is weighted equally regardless of population size.",
        icon="ℹ️",
    )

    # Filter by LGA.
    col_lga, col_status = st.columns(2)
    with col_lga:
        lgas = ["All"] + sorted(df_ward[COL_LGA].dropna().unique().tolist())
        selected_lga = st.selectbox(
            "Filter by LGA:",
            lgas,
            key=f"{MODULE_KEY}_ward_lga_filter",
        )
    with col_status:
        status_options = ["All", "Red", "Yellow", "Green", "N/A"]
        selected_status = st.selectbox(
            "Filter by Status (any indicator):",
            status_options,
            key=f"{MODULE_KEY}_ward_status_filter",
        )

    filtered_ward = df_ward.copy()
    if selected_lga != "All":
        filtered_ward = filtered_ward[filtered_ward[COL_LGA] == selected_lga]
    if selected_status != "All":
        status_cols = [c for c in _STATUS_COLS if c in filtered_ward.columns]
        if status_cols:
            mask = filtered_ward[status_cols].apply(
                lambda col: col.astype(str).str.contains(selected_status, case=False, na=False)
            ).any(axis=1)
            filtered_ward = filtered_ward[mask]

    st.caption(
        f"Displaying {len(filtered_ward):,} of {len(df_ward):,} wards"
    )
    _render_styled_table(filtered_ward, thresholds)


# ── Operational Issues ────────────────────────────────────────────────────────

def _render_issues_tab(
    df_issues: pd.DataFrame,
    df_settlement_display: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
) -> None:
    """Render operational issues analysis with filtering and settlement drill-down."""
    st.markdown("#### Operational Issues Analysis")
    st.caption(
        "Identifies wards where campaign indicators are misaligned. "
        "Uses the configured thresholds to determine High (Green) / "
        "Medium (Yellow) / Low (Red) classification."
    )

    if df_issues.empty:
        st.success(
            "No operational issues detected. All ward indicators are aligned "
            "within the configured thresholds.",
            icon="✅",
        )
        return

    # ── Issue summary KPIs ────────────────────────────────────────────────
    unique_issue_wards = df_issues[COL_WARD].nunique()
    total_issue_rows = len(df_issues)
    # Count distinct issue types present (excluding "Multiple Issues" tag).
    distinct_types = df_issues[COL_ISSUE_TYPE].nunique()

    k1, k2, k3 = st.columns(3)
    with k1:
        kpi_card("Wards with Issues", f"{unique_issue_wards}", "Unique wards affected")
    with k2:
        kpi_card("Issue Occurrences", f"{total_issue_rows}", "A ward may have multiple")
    with k3:
        kpi_card("Issue Types Found", f"{distinct_types}", "Distinct categories")

    # ── Issue type distribution ───────────────────────────────────────────
    with st.expander("📖 Issue Type Reference", expanded=False):
        ref_rows = []
        for label in ISSUE_LABELS:
            count = int((df_issues[COL_ISSUE_TYPE] == label).sum())
            if count > 0:
                ref_rows.append({
                    "Issue Type": label,
                    "Description": ISSUE_DESCRIPTIONS[label],
                    "Wards Affected": count,
                })
        if ref_rows:
            st.dataframe(
                pd.DataFrame(ref_rows),
                hide_index=True,
                use_container_width=True,
            )

    # ── Issue filter ──────────────────────────────────────────────────────
    st.markdown("##### Filter Issues")
    col_issue, col_lga = st.columns(2)
    with col_issue:
        available_issues = sorted(
            df_issues[COL_ISSUE_TYPE].unique().tolist()
        )
        issue_options = ["All Issues"] + available_issues
        selected_issue = st.selectbox(
            "Filter by Issue Type:",
            issue_options,
            key=f"{MODULE_KEY}_issue_type_filter",
        )
    with col_lga:
        issue_lgas = ["All"] + sorted(
            df_issues[COL_LGA].dropna().unique().tolist()
        )
        selected_lga = st.selectbox(
            "Filter by LGA:",
            issue_lgas,
            key=f"{MODULE_KEY}_issue_lga_filter",
        )

    filtered_issues = df_issues.copy()
    if selected_issue != "All Issues":
        filtered_issues = filtered_issues[
            filtered_issues[COL_ISSUE_TYPE] == selected_issue
        ]
    if selected_lga != "All":
        filtered_issues = filtered_issues[
            filtered_issues[COL_LGA] == selected_lga
        ]

    st.caption(
        f"Showing {len(filtered_issues):,} issue(s) affecting "
        f"{filtered_issues[COL_WARD].nunique()} ward(s)"
    )
    _render_styled_table(filtered_issues, thresholds)

    # ── Settlement drill-down ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("##### Settlement-Level Drill-Down")
    st.caption(
        "Select a ward from the issues above to see its settlement-level detail."
    )

    # Build ward options from the filtered issues table.
    affected_wards = filtered_issues[[COL_LGA, COL_WARD]].drop_duplicates()
    if affected_wards.empty:
        st.info("No wards match the current filter.", icon="ℹ️")
        return

    ward_labels = (
        affected_wards[COL_WARD] + " (" + affected_wards[COL_LGA] + ")"
    ).tolist()
    selected_ward_label = st.selectbox(
        "Select ward for drill-down:",
        ward_labels,
        key=f"{MODULE_KEY}_drilldown_ward",
    )

    if selected_ward_label:
        # Parse the selection back to LGA + Ward.
        idx = ward_labels.index(selected_ward_label)
        drill_lga = affected_wards.iloc[idx][COL_LGA]
        drill_ward = affected_wards.iloc[idx][COL_WARD]

        # Filter settlement data for this ward.
        mask = (
            (df_settlement_display[COL_LGA] == drill_lga)
            & (df_settlement_display[COL_WARD] == drill_ward)
        )
        df_drill = df_settlement_display[mask].copy()

        # Select columns for drill-down display.
        drill_cols = [
            COL_LGA, COL_WARD, COL_SETTLEMENT,
            COL_VISITATION, COL_VACCINATION, COL_HOUSEHOLD,
            STATUS_VISITATION, STATUS_VACCINATION, STATUS_HOUSEHOLD,
        ]
        available_cols = [c for c in drill_cols if c in df_drill.columns]
        df_drill = df_drill[available_cols]

        st.markdown(
            f"**{drill_ward}** ({drill_lga}) — "
            f"{len(df_drill):,} settlement(s)"
        )
        _render_styled_table(df_drill, thresholds)


# ── Downloads ─────────────────────────────────────────────────────────────────

def _render_downloads_tab(
    summary: CoverageAnalysisSummary,
    df_settlement: pd.DataFrame,
    df_ward: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
    df_issues: pd.DataFrame,
) -> None:
    """Render Excel and CSV download buttons for all outputs."""
    st.markdown("#### Export Coverage Analysis Reports")

    # ── Full Excel report ─────────────────────────────────────────────────
    excel_bytes = generate_coverage_excel_report(
        summary, df_settlement, df_ward, thresholds, df_issues
    )

    st.download_button(
        label="📄 Download Full Excel Report (.xlsx)",
        data=excel_bytes,
        file_name="Coverage_Analysis_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key=f"{MODULE_KEY}_download_excel",
    )

    st.markdown("---")
    st.markdown("##### Individual CSV Downloads")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Settlement Coverage**")
        settlement_csv = df_settlement.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=settlement_csv,
            file_name="Coverage_Settlement_Level.csv",
            mime="text/csv",
            key=f"{MODULE_KEY}_download_settlement_csv",
        )
    with c2:
        st.markdown("**Ward Coverage**")
        ward_csv = df_ward.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=ward_csv,
            file_name="Coverage_Ward_Level.csv",
            mime="text/csv",
            key=f"{MODULE_KEY}_download_ward_csv",
        )
    with c3:
        st.markdown("**Operational Issues**")
        if not df_issues.empty:
            issues_csv = df_issues.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download CSV",
                data=issues_csv,
                file_name="Coverage_Operational_Issues.csv",
                mime="text/csv",
                key=f"{MODULE_KEY}_download_issues_csv",
            )
        else:
            st.caption("No issues to export.")

    # ── Individual Excel downloads ────────────────────────────────────────
    st.markdown("---")
    st.markdown("##### Individual Excel Downloads")

    c4, c5, c6 = st.columns(3)
    with c4:
        st.markdown("**Settlement Coverage**")
        settlement_xlsx = _single_sheet_excel(df_settlement, "Settlement Coverage", thresholds)
        st.download_button(
            label="Download Excel",
            data=settlement_xlsx,
            file_name="Coverage_Settlement_Level.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{MODULE_KEY}_download_settlement_xlsx",
        )
    with c5:
        st.markdown("**Ward Coverage**")
        ward_xlsx = _single_sheet_excel(df_ward, "Ward Coverage", thresholds)
        st.download_button(
            label="Download Excel",
            data=ward_xlsx,
            file_name="Coverage_Ward_Level.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{MODULE_KEY}_download_ward_xlsx",
        )
    with c6:
        st.markdown("**Operational Issues**")
        if not df_issues.empty:
            issues_xlsx = _single_sheet_excel(df_issues, "Operational Issues", thresholds)
            st.download_button(
                label="Download Excel",
                data=issues_xlsx,
                file_name="Coverage_Operational_Issues.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{MODULE_KEY}_download_issues_xlsx",
            )
        else:
            st.caption("No issues to export.")


def _single_sheet_excel(
    df: pd.DataFrame,
    sheet_name: str,
    thresholds: dict[str, CoverageThreshold] | None = None,
) -> bytes:
    """Create a styled single-sheet Excel file from a DataFrame."""
    from io import BytesIO

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.sheets[sheet_name]
        _apply_excel_formatting(ws, sheet_name, thresholds=thresholds)
    return output.getvalue()

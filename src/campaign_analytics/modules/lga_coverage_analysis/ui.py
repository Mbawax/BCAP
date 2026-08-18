"""Streamlit UI workflow for LGA Coverage Analysis.

This module accepts LGA-level Vaccination Coverage, Household Coverage,
and Visitation data, joins them into an LGA master table, and provides
LGA-level analysis with RAG thresholds, operational issue detection,
and Excel/CSV exports.

Complete Workflow
-----------------
Data → LGA Master → Thresholds → RAG Flags
     → Operational Issues → Downloads
"""

from hashlib import sha256

import pandas as pd
import streamlit as st

from campaign_analytics.components.column_mapper import render_column_mapper
from campaign_analytics.components.data_io import read_tabular_upload, source_preview
from campaign_analytics.components.notifications import validation_messages
from campaign_analytics.components.tables import data_table
from campaign_analytics.components.upload import upload_data_file

# Reuse shared constructs from Coverage Analysis.
from campaign_analytics.modules.coverage_analysis.processor import (
    COL_HOUSEHOLD,
    COL_ISSUE_TYPE,
    COL_LGA,
    COL_VACCINATION,
    COL_VISITATION,
    CoverageThreshold,
    DEFAULT_THRESHOLDS,
    ISSUE_DESCRIPTIONS,
    ISSUE_LABELS,
    STATUS_HOUSEHOLD,
    STATUS_VACCINATION,
    STATUS_VISITATION,
    _apply_excel_formatting,
    apply_thresholds,
)

# Import LGA-specific processor functions.
from campaign_analytics.modules.lga_coverage_analysis.processor import (
    LGA_HOUSEHOLD_FIELDS,
    LGA_VACCINATION_FIELDS,
    LGA_VISITATION_FIELDS,
    LGA_VISITATION_REQUIRED_FIELDS,
    LgaCoverageAnalysisSummary,
    build_lga_master,
    detect_lga_operational_issues,
    generate_lga_coverage_excel_report,
    suggest_lga_household_mapping,
    suggest_lga_vaccination_mapping,
    suggest_lga_visitation_mapping,
    validate_lga_inputs,
)

from campaign_analytics.ui.components import kpi_card, page_header

MODULE_KEY = "lga_coverage_analysis"

# Mapping from indicator column to its status column (for display ordering).
_INDICATOR_COLS = [COL_VISITATION, COL_VACCINATION, COL_HOUSEHOLD]
_STATUS_COLS = [STATUS_VISITATION, STATUS_VACCINATION, STATUS_HOUSEHOLD]


def render_lga_coverage_analysis_module() -> None:
    """Render the complete LGA Coverage Analysis workflow."""
    _initialise_state()

    page_header(
        "LGA Coverage Analysis",
        "Analyse LGA-level campaign indicators with RAG classification "
        "and operational issue detection. Data is uploaded directly at LGA level.",
        "Campaign module",
    )

    df_vaccination, df_household, df_visitation = _render_uploads()
    if df_vaccination is None:
        st.info(
            "Please upload the **LGA-level Vaccination Coverage** dataset to proceed. "
            "This dataset provides the baseline LGA roster."
        )
        return

    vacc_mapping, hh_mapping, vis_mapping = _render_mappers(
        df_vaccination, df_household, df_visitation
    )

    _clear_stale_results(vacc_mapping, hh_mapping, vis_mapping)

    report = validate_lga_inputs(
        df_vaccination, vacc_mapping,
        df_household, hh_mapping,
        df_visitation, vis_mapping,
    )

    _render_validation(report)

    if st.button(
        "Run LGA Coverage Analysis",
        type="primary",
        disabled=not report.is_valid,
        key=f"{MODULE_KEY}_run_button",
    ):
        summary, df_lga_master = build_lga_master(
            df_vaccination=df_vaccination,
            vaccination_mapping=vacc_mapping,
            df_household=df_household,
            household_mapping=hh_mapping,
            df_visitation=df_visitation,
            visitation_mapping=vis_mapping,
        )
        st.session_state[f"{MODULE_KEY}_results"] = {
            "summary": summary,
            "lga": df_lga_master,
            "fingerprint": _compute_fingerprint(
                vacc_mapping, hh_mapping, vis_mapping
            ),
        }

    results = st.session_state.get(f"{MODULE_KEY}_results")
    if results:
        _render_results(
            results["summary"],
            results["lga"],
        )


# ── Session state ─────────────────────────────────────────────────────────────

def _initialise_state() -> None:
    """Initialize session state variables for LGA coverage analysis."""
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
    """Render upload controls for the three LGA-level input datasets."""
    st.subheader("1. File Uploads")

    c1, c2, c3 = st.columns(3)
    with c1:
        vacc_upload = upload_data_file(
            "LGA Vaccination Coverage *",
            key=f"{MODULE_KEY}_vacc_upload",
            help_text=(
                "Upload the LGA-level Vaccination Coverage dataset with "
                "LGA and Vaccination Coverage % columns."
            ),
        )
    with c2:
        hh_upload = upload_data_file(
            "LGA Household Coverage (Optional)",
            key=f"{MODULE_KEY}_hh_upload",
            help_text=(
                "Upload the LGA-level Household Coverage dataset with "
                "LGA and Household Coverage % columns."
            ),
        )
    with c3:
        vis_upload = upload_data_file(
            "LGA Visitation (Optional)",
            key=f"{MODULE_KEY}_vis_upload",
            help_text=(
                "Upload the LGA-level Visitation dataset with "
                "LGA and Visitation % columns."
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
        "Map LGA and coverage columns for accurate analysis. "
        "Data is at LGA level."
    )

    # Vaccination Coverage (Required).
    st.markdown("##### 💉 Vaccination Coverage Mappings")
    vacc_suggestions = suggest_lga_vaccination_mapping(list(df_vaccination.columns))
    vacc_mapping = render_column_mapper(
        fields=list(LGA_VACCINATION_FIELDS),
        required_fields=set(LGA_VACCINATION_FIELDS),
        source_columns=list(df_vaccination.columns),
        suggestions=vacc_suggestions,
        key_prefix=f"{MODULE_KEY}_vacc",
    )

    # Household Coverage.
    hh_mapping: dict = {}
    if df_household is not None and not df_household.empty:
        st.markdown("##### 🏠 Household Coverage Mappings")
        hh_suggestions = suggest_lga_household_mapping(list(df_household.columns))
        hh_mapping = render_column_mapper(
            fields=list(LGA_HOUSEHOLD_FIELDS),
            required_fields=set(LGA_HOUSEHOLD_FIELDS),
            source_columns=list(df_household.columns),
            suggestions=hh_suggestions,
            key_prefix=f"{MODULE_KEY}_hh",
        )

    # Visitation.
    vis_mapping: dict = {}
    if df_visitation is not None and not df_visitation.empty:
        st.markdown("##### 📍 Visitation Mappings")
        vis_suggestions = suggest_lga_visitation_mapping(list(df_visitation.columns))
        vis_mapping = render_column_mapper(
            fields=list(LGA_VISITATION_FIELDS),
            required_fields=set(LGA_VISITATION_REQUIRED_FIELDS),
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
        "indicator. These are applied as a presentation layer — the underlying "
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

            if yellow_min > green_min:
                st.warning(
                    f"{label}: Red boundary ({yellow_min}%) must be ≤ "
                    f"Green boundary ({green_min}%). Using Green boundary "
                    "as the Red boundary.",
                    icon="⚠️",
                )
                yellow_min = green_min

            updated[indicator_col] = CoverageThreshold(
                yellow_min=yellow_min, green_min=green_min
            )

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
            "🟡 Yellow": f"{threshold.yellow_min}% – {threshold.green_min - 1}%",
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
    """Format numeric coverage value as an absolute percentage string (e.g. '60%', '10%')."""
    if pd.isna(val) or val is None:
        return "N/A"
    try:
        num = float(val)
        return f"{int(round(num))}%"
    except (ValueError, TypeError):
        return str(val)


def _style_dataframe(
    df: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
) -> object:
    """Apply background colors to percentage indicator columns based on thresholds and 100 rule."""
    def _color_indicator_cell(val, indicator_col: str) -> str:
        if pd.isna(val) or val is None:
            return "background-color: #F3F4F6; color: #6B7280"
        try:
            num_val = float(val)
        except (ValueError, TypeError):
            return ""

        if num_val >= 100.0:
            return "background-color: #BBF7D0; color: #166534"

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
    summary: LgaCoverageAnalysisSummary,
    df_lga: pd.DataFrame,
) -> None:
    """Render threshold config, then tabs for results."""
    st.markdown("---")

    thresholds = _render_threshold_config()

    df_lga_display = apply_thresholds(df_lga, thresholds)
    df_issues = detect_lga_operational_issues(df_lga, thresholds)

    st.subheader("4. LGA Coverage Analysis Results")

    tab_summary, tab_lga, tab_issues, tab_downloads = st.tabs([
        "📊 Summary",
        "🏛️ LGA Level",
        "⚠️ Operational Issues",
        "📥 Downloads & Export",
    ])

    with tab_summary:
        _render_summary_tab(summary, df_lga, df_issues)

    with tab_lga:
        _render_lga_tab(df_lga_display, thresholds)

    with tab_issues:
        _render_issues_tab(df_issues, thresholds)

    with tab_downloads:
        _render_downloads_tab(
            summary, df_lga_display, thresholds, df_issues,
        )


def _render_summary_tab(
    summary: LgaCoverageAnalysisSummary,
    df_lga: pd.DataFrame,
    df_issues: pd.DataFrame,
) -> None:
    """Render KPI cards."""
    k1, k2 = st.columns(2)
    with k1:
        kpi_card(
            "Total LGAs",
            f"{summary.total_lgas:,}",
            "Local Government Areas Analysed",
        )
    with k2:
        wards_with_issues = (
            df_issues[COL_LGA].nunique() if not df_issues.empty else 0
        )
        kpi_card(
            "LGAs with Issues",
            f"{wards_with_issues}",
            f"of {summary.total_lgas} total LGAs",
        )

    k3, k4, k5 = st.columns(3)
    with k3:
        kpi_card(
            "Avg. Visitation",
            f"{int(round(summary.avg_visitation_pct))}%",
            "Mean across LGAs",
        )
    with k4:
        kpi_card(
            "Avg. Vaccination Coverage",
            f"{int(round(summary.avg_vaccination_pct))}%",
            "Mean across LGAs",
        )
    with k5:
        kpi_card(
            "Avg. Household Coverage",
            f"{int(round(summary.avg_household_pct))}%",
            "Mean across LGAs",
        )


def _render_lga_tab(
    df_lga: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
) -> None:
    """Render LGA-level master table with conditional formatting."""
    st.markdown("#### LGA-Level Coverage Table")
    st.info(
        "**Data uploaded at LGA level.** Values are as reported per Local Government Area.",
        icon="ℹ️",
    )

    col_lga, col_status = st.columns(2)
    with col_lga:
        lgas = ["All"] + sorted(df_lga[COL_LGA].dropna().unique().tolist())
        selected_lga = st.selectbox(
            "Filter by LGA:",
            lgas,
            key=f"{MODULE_KEY}_lga_filter",
        )
    with col_status:
        status_options = ["All", "Red", "Yellow", "Green", "N/A"]
        selected_status = st.selectbox(
            "Filter by Status (any indicator):",
            status_options,
            key=f"{MODULE_KEY}_lga_status_filter",
        )

    filtered_lga = df_lga.copy()
    if selected_lga != "All":
        filtered_lga = filtered_lga[filtered_lga[COL_LGA] == selected_lga]
    if selected_status != "All":
        status_cols = [c for c in _STATUS_COLS if c in filtered_lga.columns]
        if status_cols:
            mask = filtered_lga[status_cols].apply(
                lambda col: col.astype(str).str.contains(selected_status, case=False, na=False)
            ).any(axis=1)
            filtered_lga = filtered_lga[mask]

    st.caption(
        f"Displaying {len(filtered_lga):,} of {len(df_lga):,} LGAs"
    )
    _render_styled_table(filtered_lga, thresholds)


# ── Operational Issues ────────────────────────────────────────────────────────

def _render_issues_tab(
    df_issues: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
) -> None:
    """Render operational issues analysis with filtering."""
    st.markdown("#### Operational Issues Analysis")
    st.caption(
        "Identifies LGAs where campaign indicators are misaligned. "
        "Uses the configured thresholds to determine High (Green) / "
        "Medium (Yellow) / Low (Red) classification."
    )

    if df_issues.empty:
        st.success(
            "No operational issues detected. All LGA indicators are aligned "
            "within the configured thresholds.",
            icon="✅",
        )
        return

    # ── Issue summary KPIs ────────────────────────────────────────────────
    unique_issue_lgas = df_issues[COL_LGA].nunique()
    total_issue_rows = len(df_issues)
    distinct_types = df_issues[COL_ISSUE_TYPE].nunique()

    k1, k2, k3 = st.columns(3)
    with k1:
        kpi_card("LGAs with Issues", f"{unique_issue_lgas}", "Unique LGAs affected")
    with k2:
        kpi_card("Issue Occurrences", f"{total_issue_rows}", "An LGA may have multiple")
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
                    "LGAs Affected": count,
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
        f"{filtered_issues[COL_LGA].nunique()} LGA(s)"
    )
    _render_styled_table(filtered_issues, thresholds)


# ── Downloads ─────────────────────────────────────────────────────────────────

def _render_downloads_tab(
    summary: LgaCoverageAnalysisSummary,
    df_lga: pd.DataFrame,
    thresholds: dict[str, CoverageThreshold],
    df_issues: pd.DataFrame,
) -> None:
    """Render Excel and CSV download buttons for all outputs."""
    st.markdown("#### Export LGA Coverage Analysis Reports")

    excel_bytes = generate_lga_coverage_excel_report(
        summary, df_lga, thresholds, df_issues
    )

    st.download_button(
        label="📄 Download Full Excel Report (.xlsx)",
        data=excel_bytes,
        file_name="LGA_Coverage_Analysis_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key=f"{MODULE_KEY}_download_excel",
    )

    st.markdown("---")
    st.markdown("##### Individual CSV Downloads")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**LGA Coverage**")
        lga_csv = df_lga.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=lga_csv,
            file_name="LGA_Coverage_Level.csv",
            mime="text/csv",
            key=f"{MODULE_KEY}_download_lga_csv",
        )
    with c2:
        st.markdown("**Operational Issues**")
        if not df_issues.empty:
            issues_csv = df_issues.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download CSV",
                data=issues_csv,
                file_name="LGA_Coverage_Operational_Issues.csv",
                mime="text/csv",
                key=f"{MODULE_KEY}_download_issues_csv",
            )
        else:
            st.caption("No issues to export.")

    st.markdown("---")
    st.markdown("##### Individual Excel Downloads")

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**LGA Coverage**")
        lga_xlsx = _single_sheet_excel(df_lga, "LGA Coverage", thresholds)
        st.download_button(
            label="Download Excel",
            data=lga_xlsx,
            file_name="LGA_Coverage_Level.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{MODULE_KEY}_download_lga_xlsx",
        )
    with c4:
        st.markdown("**Operational Issues**")
        if not df_issues.empty:
            issues_xlsx = _single_sheet_excel(df_issues, "Operational Issues", thresholds)
            st.download_button(
                label="Download Excel",
                data=issues_xlsx,
                file_name="LGA_Coverage_Operational_Issues.xlsx",
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

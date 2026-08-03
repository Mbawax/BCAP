"""Streamlit UI workflow for Settlement Analysis & Triangulation."""

from hashlib import sha256

import pandas as pd
import streamlit as st

from campaign_analytics.components.column_mapper import render_column_mapper
from campaign_analytics.components.data_io import read_tabular_upload, source_preview
from campaign_analytics.components.notifications import validation_messages
from campaign_analytics.components.tables import data_table
from campaign_analytics.components.upload import upload_data_file
from campaign_analytics.modules.settlement_analysis.charts import (
    build_lga_coverage_chart,
    build_source_coverage_chart,
    build_status_distribution_chart,
)
from campaign_analytics.modules.settlement_analysis.processor import (
    REQUIRED_FIELDS,
    SettlementAnalysisSummary,
    generate_settlement_excel_report,
    process_settlement_analysis,
    suggest_settlement_mapping,
    validate_inputs,
)
from campaign_analytics.ui.components import kpi_card, page_header

MODULE_KEY = "settlement_analysis"


def render_settlement_analysis_module() -> None:
    """Render the complete 4-dataset Settlement Analysis workflow."""
    _initialise_state()

    page_header(
        "Settlement Analysis",
        "Triangulate settlement-level visitation across Planned Settlements baseline, "
        "GTS Visitation, eTally, and MST tracking sources.",
        "Campaign module",
    )

    df_planned, df_gts, df_etally, df_mst = _render_uploads()
    if df_planned is None:
        st.info("Please upload the **Planned Settlements (Baseline)** dataset to proceed.")
        return

    planned_mapping, gts_mapping, etally_mapping, mst_mapping = _render_mappers(
        df_planned, df_gts, df_etally, df_mst
    )

    _clear_stale_results(planned_mapping, gts_mapping, etally_mapping, mst_mapping)

    report = validate_inputs(
        df_planned,
        planned_mapping,
        df_gts,
        gts_mapping,
        df_etally,
        etally_mapping,
        df_mst,
        mst_mapping,
    )

    _render_validation(report)

    if st.button(
        "Run Settlement Triangulation Analysis",
        type="primary",
        disabled=not report.is_valid,
        key=f"{MODULE_KEY}_run_button",
    ):
        summary, df_lga_summary, df_linelist = process_settlement_analysis(
            df_planned=df_planned,
            planned_mapping=planned_mapping,
            df_gts=df_gts,
            gts_mapping=gts_mapping,
            df_etally=df_etally,
            etally_mapping=etally_mapping,
            df_mst=df_mst,
            mst_mapping=mst_mapping,
        )
        st.session_state[f"{MODULE_KEY}_results"] = {
            "summary": summary,
            "lga_summary": df_lga_summary,
            "linelist": df_linelist,
            "fingerprint": _compute_fingerprint(planned_mapping, gts_mapping, etally_mapping, mst_mapping),
        }

    results = st.session_state.get(f"{MODULE_KEY}_results")
    if results:
        _render_results(
            results["summary"],
            results["lga_summary"],
            results["linelist"],
        )


def _initialise_state() -> None:
    """Initialize session state variables for settlement analysis."""
    defaults = {
        f"{MODULE_KEY}_planned_file": None,
        f"{MODULE_KEY}_gts_file": None,
        f"{MODULE_KEY}_etally_file": None,
        f"{MODULE_KEY}_mst_file": None,
        f"{MODULE_KEY}_results": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_uploads() -> tuple[
    pd.DataFrame | None,
    pd.DataFrame | None,
    pd.DataFrame | None,
    pd.DataFrame | None,
]:
    """Render upload tabs for Planned Settlements (Baseline), GTS, eTally, and MST."""
    st.subheader("1. File Uploads")

    c1, c2 = st.columns(2)
    with c1:
        planned_upload = upload_data_file(
            "Planned Settlements (Baseline) *",
            key=f"{MODULE_KEY}_planned_upload",
            help_text="Upload Planned Settlements master list (CSV or Excel).",
        )
    with c2:
        gts_upload = upload_data_file(
            "GTS Visitation (Optional)",
            key=f"{MODULE_KEY}_gts_upload",
            help_text="Upload GTS Visitation status dataset.",
        )

    c3, c4 = st.columns(2)
    with c3:
        etally_upload = upload_data_file(
            "eTally Dataset (Optional)",
            key=f"{MODULE_KEY}_etally_upload",
            help_text="Upload eTally settlement dataset.",
        )
    with c4:
        mst_upload = upload_data_file(
            "MST Dataset (Optional)",
            key=f"{MODULE_KEY}_mst_upload",
            help_text="Upload MST / Supervisor tracking dataset.",
        )

    df_planned = _load_dataframe(planned_upload, "planned")
    df_gts = _load_dataframe(gts_upload, "gts")
    df_etally = _load_dataframe(etally_upload, "etally")
    df_mst = _load_dataframe(mst_upload, "mst")

    with st.expander("Uploaded Datasets Preview"):
        if df_planned is not None and planned_upload:
            source_preview(df_planned, planned_upload.name)
        if df_gts is not None and gts_upload:
            source_preview(df_gts, gts_upload.name)
        if df_etally is not None and etally_upload:
            source_preview(df_etally, etally_upload.name)
        if df_mst is not None and mst_upload:
            source_preview(df_mst, mst_upload.name)

    return df_planned, df_gts, df_etally, df_mst


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


def _render_mappers(
    df_planned: pd.DataFrame,
    df_gts: pd.DataFrame | None,
    df_etally: pd.DataFrame | None,
    df_mst: pd.DataFrame | None,
) -> tuple[dict, dict, dict, dict]:
    """Render column mapping UI sections for all uploaded datasets."""
    st.subheader("2. Column Mappings")
    st.caption("Map LGA, Ward, and Settlement columns for accurate triangulation.")

    # Planned Settlements (Required)
    st.markdown("##### 📍 Planned Settlements (Baseline) Mappings")
    planned_suggestions = suggest_settlement_mapping(list(df_planned.columns))
    planned_mapping = render_column_mapper(
        fields=list(REQUIRED_FIELDS),
        required_fields=set(REQUIRED_FIELDS),
        source_columns=list(df_planned.columns),
        suggestions=planned_suggestions,
        key_prefix=f"{MODULE_KEY}_planned",
    )

    # GTS Mappings
    gts_mapping = {}
    if df_gts is not None and not df_gts.empty:
        st.markdown("##### 📡 GTS Visitation Mappings")
        gts_suggestions = suggest_settlement_mapping(list(df_gts.columns))
        gts_mapping = render_column_mapper(
            fields=list(REQUIRED_FIELDS),
            required_fields=set(REQUIRED_FIELDS),
            source_columns=list(df_gts.columns),
            suggestions=gts_suggestions,
            key_prefix=f"{MODULE_KEY}_gts",
        )

    # eTally Mappings
    etally_mapping = {}
    if df_etally is not None and not df_etally.empty:
        st.markdown("##### 📱 eTally Mappings")
        etally_suggestions = suggest_settlement_mapping(list(df_etally.columns))
        etally_mapping = render_column_mapper(
            fields=list(REQUIRED_FIELDS),
            required_fields=set(REQUIRED_FIELDS),
            source_columns=list(df_etally.columns),
            suggestions=etally_suggestions,
            key_prefix=f"{MODULE_KEY}_etally",
        )

    # MST Mappings
    mst_mapping = {}
    if df_mst is not None and not df_mst.empty:
        st.markdown("##### 📋 MST / Supervisor Mappings")
        mst_suggestions = suggest_settlement_mapping(list(df_mst.columns))
        mst_mapping = render_column_mapper(
            fields=list(REQUIRED_FIELDS),
            required_fields=set(REQUIRED_FIELDS),
            source_columns=list(df_mst.columns),
            suggestions=mst_suggestions,
            key_prefix=f"{MODULE_KEY}_mst",
        )

    return planned_mapping, gts_mapping, etally_mapping, mst_mapping


def _render_validation(report) -> None:
    """Render error and warning notifications from validation report."""
    validation_messages(report.errors, report.warnings)


def _clear_stale_results(p_map, g_map, e_map, m_map) -> None:
    """Clear session state results if mapping input fingerprint changes."""
    fingerprint = _compute_fingerprint(p_map, g_map, e_map, m_map)
    results = st.session_state.get(f"{MODULE_KEY}_results")
    if results and results.get("fingerprint") != fingerprint:
        st.session_state[f"{MODULE_KEY}_results"] = None


def _compute_fingerprint(p_map, g_map, e_map, m_map) -> str:
    """Compute string hash of current user column selections."""
    raw = f"{p_map}|{g_map}|{e_map}|{m_map}"
    return sha256(raw.encode("utf-8")).hexdigest()


def _render_results(
    summary: SettlementAnalysisSummary,
    df_lga_summary: pd.DataFrame,
    df_linelist: pd.DataFrame,
) -> None:
    """Render tabs for Summary, LGA Coverage, Settlement Linelist, and Downloads."""
    st.markdown("---")
    st.subheader("3. Settlement Analysis Results")

    tab_summary, tab_lga, tab_linelist, tab_downloads = st.tabs([
        "📊 Campaign Summary",
        "🗺️ LGA Coverage & Summary",
        "📋 Settlement Linelist",
        "📥 Downloads & Export",
    ])

    with tab_summary:
        _render_summary_tab(summary)

    with tab_lga:
        _render_lga_tab(df_lga_summary)

    with tab_linelist:
        _render_linelist_tab(df_linelist)

    with tab_downloads:
        _render_downloads_tab(summary, df_lga_summary, df_linelist)


def _render_summary_tab(summary: SettlementAnalysisSummary) -> None:
    """Render KPI cards and overall coverage charts."""
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card("Planned Settlements", f"{summary.total_planned:,}", "Baseline Count")
    with k2:
        kpi_card("GTS Visited", f"{summary.gts_visited_count:,}", f"{summary.gts_coverage_pct}% Coverage")
    with k3:
        kpi_card("eTally Visited", f"{summary.etally_visited_count:,}", f"{summary.etally_coverage_pct}% Coverage")
    with k4:
        kpi_card("MST Visited", f"{summary.mst_visited_count:,}", f"{summary.mst_coverage_pct}% Coverage")

    k5, k6, k7, k8 = st.columns(4)
    with k5:
        kpi_card("MST + eTally Visited", f"{summary.mst_etally_visited_count:,}", f"{summary.mst_etally_coverage_pct}% Coverage")
    with k6:
        kpi_card("All Sources Visited", f"{summary.all_sources_visited_count:,}", f"{summary.all_sources_coverage_pct}% Coverage")
    with k7:
        kpi_card("Any Source Visited", f"{summary.any_source_visited_count:,}", f"{summary.any_source_coverage_pct}% Coverage")
    with k8:
        kpi_card("Unvisited Settlements", f"{summary.unvisited_count:,}", f"{summary.unvisited_pct}% Unvisited")

    st.markdown("#### Visitation Coverage Breakdown")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(build_source_coverage_chart(summary), use_container_width=True)
    with c2:
        st.plotly_chart(build_status_distribution_chart(st.session_state[f"{MODULE_KEY}_results"]["linelist"]), use_container_width=True)


def _render_lga_tab(df_lga_summary: pd.DataFrame) -> None:
    """Render LGA level summary table and comparison chart."""
    st.markdown("#### LGA Coverage Comparison")
    st.plotly_chart(build_lga_coverage_chart(df_lga_summary), use_container_width=True)

    st.markdown("#### LGA Level Coverage Summary Table")
    data_table(df_lga_summary, key=f"{MODULE_KEY}_lga_table")


def _render_linelist_tab(df_linelist: pd.DataFrame) -> None:
    """Render interactive settlement-level linelist table."""
    st.markdown("#### Detailed Settlement Triangulation Linelist")

    # Filter controls
    col_lga, col_status = st.columns(2)
    with col_lga:
        lgas = ["All"] + sorted(list(df_linelist["LGA"].dropna().unique()))
        selected_lga = st.selectbox("Filter by LGA:", lgas, key=f"{MODULE_KEY}_lga_filter")
    with col_status:
        statuses = ["All"] + sorted(list(df_linelist["Overall_Visitation_Status"].dropna().unique()))
        selected_status = st.selectbox("Filter by Visitation Status:", statuses, key=f"{MODULE_KEY}_status_filter")

    filtered = df_linelist.copy()
    if selected_lga != "All":
        filtered = filtered[filtered["LGA"] == selected_lga]
    if selected_status != "All":
        filtered = filtered[filtered["Overall_Visitation_Status"] == selected_status]

    st.caption(f"Displaying {len(filtered):,} of {len(df_linelist):,} planned settlements")
    data_table(filtered, key=f"{MODULE_KEY}_linelist_table")


def _render_downloads_tab(
    summary: SettlementAnalysisSummary,
    df_lga_summary: pd.DataFrame,
    df_linelist: pd.DataFrame,
) -> None:
    """Render multi-sheet Excel and CSV download buttons."""
    st.markdown("#### Export Settlement Analysis Reports")

    excel_bytes = generate_settlement_excel_report(summary, df_lga_summary, df_linelist)

    st.download_button(
        label="📄 Download Multi-Sheet Excel Report (.xlsx)",
        data=excel_bytes,
        file_name="Settlement_Analysis_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key=f"{MODULE_KEY}_download_excel",
    )

    st.markdown("---")
    st.markdown("##### Individual CSV Downloads")

    c1, c2 = st.columns(2)
    with c1:
        lga_csv = df_lga_summary.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download LGA Coverage Summary (CSV)",
            data=lga_csv,
            file_name="LGA_Settlement_Coverage_Summary.csv",
            mime="text/csv",
            key=f"{MODULE_KEY}_download_lga_csv",
        )
    with c2:
        linelist_csv = df_linelist.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download Settlement Linelist (CSV)",
            data=linelist_csv,
            file_name="Settlement_Triangulation_Linelist.csv",
            mime="text/csv",
            key=f"{MODULE_KEY}_download_linelist_csv",
        )

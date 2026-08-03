"""Streamlit interface for separate nOPV and bOPV coverage analyses.

nOPV is rendered first in full, followed by bOPV below — never combined.
A single reusable helper ``_render_vaccine_section`` eliminates duplicated
rendering code across the two vaccines.
"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pandas as pd
import streamlit as st

from campaign_analytics.components.column_mapper import render_column_mapper
from campaign_analytics.components.data_io import read_tabular_upload, source_preview
from campaign_analytics.components.layout import section_heading
from campaign_analytics.components.notifications import validation_messages
from campaign_analytics.components.tables import data_table
from campaign_analytics.components.upload import upload_data_file
from campaign_analytics.modules.vaccination.charts import (
    coverage_by_lga,
    coverage_gauge,
    vaccinated_vs_remaining,
)
from campaign_analytics.modules.vaccination.processor import (
    ETALLY_FIELDS,
    SUMMARY_COLUMNS,
    TARGET_FIELDS,
    VACCINES,
    Mapping,
    VaccineAnalysis,
    process_all_vaccines,
    suggest_etally_mapping,
    suggest_target_mapping,
)
from campaign_analytics.modules.vaccination.validators import validate_inputs
from campaign_analytics.ui.components import kpi_card, page_header

MODULE_KEY = "vaccination_analysis"


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def render_vaccination_module() -> None:
    """Render the complete two-source vaccination analysis workflow."""
    _initialise_state()
    page_header(
        "Vaccination Analysis",
        "Analyse nOPV and bOPV coverage independently using mapped eTally and "
        "target-population datasets.",
        "Campaign module",
    )

    # ── Step 1: Uploads ──────────────────────────────────────────────────────
    target_source, etally_source = _render_uploads()
    if target_source is None or etally_source is None:
        return

    # ── Step 2: Column mapping ───────────────────────────────────────────────
    target_mapping, etally_mapping = _render_mappers(target_source, etally_source)

    st.divider()
    if st.button(
        "Apply Column Mappings & Validate",
        type="primary",
        key="btn_apply_mappings",
    ):
        _save_mappings(target_mapping, etally_mapping)
        st.rerun()

    # ── Step 3: Validation ───────────────────────────────────────────────────
    applied = st.session_state[MODULE_KEY]["applied_mappings"]
    if applied is None:
        st.info(
            "Select your columns above, then click "
            "**Apply Column Mappings & Validate**."
        )
        return

    applied_target_mapping, applied_etally_mapping = applied

    if (target_mapping, etally_mapping) != applied:
        st.warning(
            "You have changed a column selection. "
            "Click **Apply Column Mappings & Validate** to update."
        )

    report = validate_inputs(
        target_source, etally_source,
        applied_target_mapping, applied_etally_mapping,
    )
    _render_validation(report)

    if not report.is_valid:
        st.error("Fix the validation errors above before running the analysis.")
        return

    # ── Step 4: Run analysis ─────────────────────────────────────────────────
    if st.button(
        "Run Vaccine Analysis",
        type="primary",
        key="btn_run_analysis",
    ):
        with st.spinner("Processing nOPV and bOPV analyses independently…"):
            analyses = process_all_vaccines(
                target_source, etally_source,
                applied_target_mapping, applied_etally_mapping,
            )
        st.session_state[MODULE_KEY]["analyses"] = analyses
        st.session_state[MODULE_KEY]["processed_mappings"] = applied
        st.rerun()

    # ── Step 5: Results (sequential — nOPV first, then bOPV) ─────────────────
    analyses = st.session_state[MODULE_KEY]["analyses"]
    if analyses:
        _render_results(analyses)


# ═══════════════════════════════════════════════════════════════════════════════
# State management
# ═══════════════════════════════════════════════════════════════════════════════

def _initialise_state() -> None:
    """Ensure all required session-state keys exist."""
    st.session_state.setdefault(
        MODULE_KEY,
        {
            "input_signature": None,
            "analyses": None,
            "processed_mappings": None,
            "applied_mappings": None,
        },
    )


def _save_mappings(target_mapping: Mapping, etally_mapping: Mapping) -> None:
    """Persist confirmed mappings and clear stale results if mappings changed."""
    state = st.session_state[MODULE_KEY]
    new_mappings = (target_mapping, etally_mapping)
    if state["processed_mappings"] and state["processed_mappings"] != new_mappings:
        state["analyses"] = None
        state["processed_mappings"] = None
    state["applied_mappings"] = new_mappings


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Upload
# ═══════════════════════════════════════════════════════════════════════════════

def _render_uploads() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Render the upload controls and return both source DataFrames."""
    with st.expander("Step 1 — Upload source datasets", expanded=True):
        target_col, etally_col = st.columns(2)
        with target_col:
            target_file = upload_data_file(
                "Target Population file",
                "vaccination_target_file",
                "Required columns: LGA and Target Population.",
            )
        with etally_col:
            etally_file = upload_data_file(
                "eTally file",
                "vaccination_etally_file",
                "Required columns: LGA, nOPV Vaccinated, and bOPV Vaccinated.",
            )
        if target_file is None or etally_file is None:
            st.info("Upload both files to begin column mapping and validation.")
            return None, None

        target_content = target_file.getvalue()
        etally_content = etally_file.getvalue()
        signature = _input_signature(target_content, etally_content)

        # Reset state when source files change
        if st.session_state[MODULE_KEY]["input_signature"] != signature:
            st.session_state[MODULE_KEY] = {
                "input_signature": signature,
                "analyses": None,
                "processed_mappings": None,
                "applied_mappings": None,
            }

        try:
            target_source = read_tabular_upload(target_content, target_file.name)
            etally_source = read_tabular_upload(etally_content, etally_file.name)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            st.error(f"One of the uploaded files could not be read: {exc}")
            return None, None

        if target_source.empty or etally_source.empty:
            st.error("Both source files must contain at least one data row.")
            return None, None

        source_preview(target_source, target_file.name)
        source_preview(etally_source, etally_file.name)
        return target_source, etally_source


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2 — Column mapping
# ═══════════════════════════════════════════════════════════════════════════════

def _render_mappers(
    target_source: pd.DataFrame,
    etally_source: pd.DataFrame,
) -> tuple[Mapping, Mapping]:
    """Render column mappers for both datasets and return the mappings."""
    with st.expander("Step 2 — Column mapping", expanded=True):
        target_tab, etally_tab = st.tabs(["Target Population", "eTally"])
        with target_tab:
            st.caption(
                "Map the Target Population source fields. Both fields are required."
            )
            target_mapping = render_column_mapper(
                list(TARGET_FIELDS),
                set(TARGET_FIELDS),
                list(target_source.columns),
                suggest_target_mapping(list(target_source.columns)),
                f"vaccination_target_{st.session_state[MODULE_KEY]['input_signature']}",
            )
        with etally_tab:
            st.caption("Map the eTally source fields. All fields are required.")
            etally_mapping = render_column_mapper(
                list(ETALLY_FIELDS),
                set(ETALLY_FIELDS),
                list(etally_source.columns),
                suggest_etally_mapping(list(etally_source.columns)),
                f"vaccination_etally_{st.session_state[MODULE_KEY]['input_signature']}",
            )
    return target_mapping, etally_mapping


# ═══════════════════════════════════════════════════════════════════════════════
# Step 3 — Validation
# ═══════════════════════════════════════════════════════════════════════════════

def _render_validation(report) -> None:
    """Show validation results in an expander."""
    with st.expander("Step 3 — Validation", expanded=True):
        validation_messages(report.errors, report.warnings)
        if report.is_valid:
            st.success(
                "Both datasets are valid and ready for independent processing."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Step 4–5 — Results
# ═══════════════════════════════════════════════════════════════════════════════

def _render_results(analyses: dict[str, VaccineAnalysis]) -> None:
    """Render nOPV and bOPV analyses sequentially (nOPV first, then bOPV)."""
    st.divider()
    section_heading("Analysis Results", "nOPV and bOPV are processed independently.")

    for definition in VACCINES:
        analysis = analyses[definition.code]
        _render_vaccine_section(analysis)
        st.markdown("")  # spacing between vaccine sections


def _render_vaccine_section(analysis: VaccineAnalysis) -> None:
    """Render KPIs, charts, table, and downloads for a single vaccine.

    This is the single reusable helper that eliminates duplicate code — called
    once for nOPV and once for bOPV.
    """
    vaccine = analysis.definition
    summary = analysis.summary

    with st.container(border=True):
        st.subheader(f"{vaccine.label} Coverage Analysis")

        # ── KPI cards ────────────────────────────────────────────────────
        kpi_cols = st.columns(4)
        metrics = [
            ("Target Population", f"{summary.target_population:,}", "From mapped target data"),
            ("Vaccinated", f"{summary.vaccinated:,}", f"Total {vaccine.label} doses"),
            ("Remaining", f"{summary.remaining:,}", "Not yet vaccinated"),
            (
                "Coverage",
                _format_percent(summary.coverage_percent),
                f"Across {summary.lga_count} LGA(s)",
            ),
        ]
        for col, (label, value, detail) in zip(kpi_cols, metrics, strict=True):
            with col:
                kpi_card(label, value, detail)

        st.markdown("")  # spacing

        # ── Charts ───────────────────────────────────────────────────────
        gauge_col, bar_col = st.columns([1, 2])
        with gauge_col:
            st.plotly_chart(
                coverage_gauge(summary.coverage_percent, vaccine.label),
                key=f"gauge_{vaccine.code}",
            )
        with bar_col:
            st.plotly_chart(
                coverage_by_lga(analysis.lga_summary, vaccine.label),
                key=f"coverage_{vaccine.code}",
            )

        st.plotly_chart(
            vaccinated_vs_remaining(analysis.lga_summary, vaccine.label),
            key=f"stacked_{vaccine.code}",
        )

        # ── Summary table ────────────────────────────────────────────────
        st.markdown(f"#### {vaccine.label} — LGA Summary")
        data_table(
            analysis.lga_summary,
            height=min(450, max(200, len(analysis.lga_summary) * 38 + 40)),
        )

        # ── Downloads ────────────────────────────────────────────────────
        dl_left, dl_right = st.columns(2)
        filename_base = f"{vaccine.label}_vaccination_coverage_analysis"
        with dl_left:
            st.download_button(
                f"Download {vaccine.label} summary (CSV)",
                analysis.lga_summary.to_csv(index=False).encode("utf-8"),
                f"{filename_base}.csv",
                "text/csv",
                key=f"dl_csv_{vaccine.code}",
            )
        with dl_right:
            st.download_button(
                f"Download {vaccine.label} summary (Excel)",
                _to_excel(analysis),
                f"{filename_base}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_xlsx_{vaccine.code}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Export helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _to_excel(analysis: VaccineAnalysis) -> bytes:
    """Build an Excel workbook with LGA detail and summary KPI sheets."""
    output = BytesIO()
    summary = analysis.summary
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        analysis.lga_summary.to_excel(
            writer, sheet_name="LGA Coverage", index=False,
        )
        pd.DataFrame([
            {"Metric": "Vaccine", "Value": analysis.definition.label},
            {"Metric": "Total Target Population", "Value": summary.target_population},
            {"Metric": "Total Vaccinated", "Value": summary.vaccinated},
            {"Metric": "Total Remaining", "Value": summary.remaining},
            {"Metric": "Overall Coverage (%)", "Value": summary.coverage_percent},
            {"Metric": "Number of LGAs", "Value": summary.lga_count},
        ]).to_excel(writer, sheet_name="Summary KPIs", index=False)
    return output.getvalue()


def _input_signature(target_content: bytes, etally_content: bytes) -> str:
    """Create a hash signature for the uploaded file pair."""
    return sha256(target_content + etally_content).hexdigest()


def _format_percent(value: float | None) -> str:
    """Format a coverage percentage or return a dash for None."""
    return f"{value:.1f}%" if value is not None else "–"

"""Streamlit workflow for LGA-level planned-versus-reported team analysis."""

from hashlib import sha256
from io import BytesIO

import pandas as pd
import streamlit as st

from campaign_analytics.components.column_mapper import render_column_mapper
from campaign_analytics.components.data_io import read_tabular_upload, source_preview
from campaign_analytics.components.notifications import validation_messages
from campaign_analytics.components.tables import data_table
from campaign_analytics.components.upload import upload_data_file
from campaign_analytics.modules.teams_reporting.charts import (
    reporting_rate_by_lga,
    team_status_by_lga,
)
from campaign_analytics.modules.teams_reporting.processor import (
    DISTRIBUTION_FIELDS,
    DistributionMapping,
    ETallyMapping,
    TeamsReportingSummary,
    process_data,
    suggest_distribution_mapping,
    suggest_etally_lga,
)
from campaign_analytics.modules.teams_reporting.validators import validate_inputs
from campaign_analytics.ui.components import kpi_card, page_header

MODULE_KEY = "teams_reporting"


def render_teams_reporting_module() -> None:
    """Render the complete eTally and Team Distribution workflow."""
    _initialise_state()
    page_header(
        "Teams Reporting",
        "Build unique Team IDs from eTally, then compare reported teams with LGA "
        "team-distribution plans.",
        "Campaign module",
    )
    etally_source, distribution_source = _render_uploads()
    if etally_source is None or distribution_source is None:
        return
    etally_mapping, distribution_mapping = _render_mappers(
        etally_source,
        distribution_source,
    )
    _clear_stale_results(etally_mapping, distribution_mapping)
    report = validate_inputs(
        etally_source,
        distribution_source,
        etally_mapping,
        distribution_mapping,
    )
    _render_validation(report)
    if st.button(
        "Process team reporting",
        type="primary",
        disabled=not report.is_valid,
    ):
        result, summary = process_data(
            etally_source,
            distribution_source,
            etally_mapping,
            distribution_mapping,
        )
        st.session_state[MODULE_KEY]["result"] = result
        st.session_state[MODULE_KEY]["summary"] = summary
        st.session_state[MODULE_KEY]["processed_mappings"] = (
            etally_mapping,
            distribution_mapping,
        )
        st.success("Team reporting results were processed successfully.")

    result = st.session_state[MODULE_KEY]["result"]
    summary = st.session_state[MODULE_KEY]["summary"]
    if result is not None and summary is not None:
        _render_results(result, summary)


def _initialise_state() -> None:
    st.session_state.setdefault(
        MODULE_KEY,
        {
            "input_signature": None,
            "result": None,
            "summary": None,
            "processed_mappings": None,
        },
    )


def _render_uploads() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    with st.expander("1. Upload source datasets", expanded=True):
        etally_column, distribution_column = st.columns(2)
        with etally_column:
            etally_file = upload_data_file(
                "eTally file",
                "teams_reporting_etally_file",
                "CSV and Excel files are supported.",
            )
        with distribution_column:
            distribution_file = upload_data_file(
                "Team Distribution file",
                "teams_reporting_distribution_file",
                "CSV and Excel files are supported.",
            )
        if etally_file is None or distribution_file is None:
            st.info("Upload both eTally and Team Distribution files to continue.")
            return None, None
        etally_content = etally_file.getvalue()
        distribution_content = distribution_file.getvalue()
        signature = _input_signature(etally_content, distribution_content)
        if st.session_state[MODULE_KEY]["input_signature"] != signature:
            st.session_state[MODULE_KEY] = {
                "input_signature": signature,
                "result": None,
                "summary": None,
                "processed_mappings": None,
            }
        try:
            etally_source = read_tabular_upload(etally_content, etally_file.name)
            distribution_source = read_tabular_upload(
                distribution_content,
                distribution_file.name,
            )
        except (OSError, UnicodeDecodeError, ValueError) as error:
            st.error(f"One of the uploaded files could not be read: {error}")
            return None, None
        if etally_source.empty or distribution_source.empty:
            st.error("Both uploaded files must contain at least one data row.")
            return None, None
        source_preview(etally_source, etally_file.name)
        source_preview(distribution_source, distribution_file.name)
        return etally_source, distribution_source


def _render_mappers(
    etally_source: pd.DataFrame,
    distribution_source: pd.DataFrame,
) -> tuple[ETallyMapping, DistributionMapping]:
    with st.expander("2. Column mapping", expanded=True):
        etally_tab, distribution_tab = st.tabs(["eTally", "Team Distribution"])
        with etally_tab:
            st.caption(
                "Map the LGA, then select exactly two or three source columns to "
                "make each Team ID. The selected ID columns must include LGA."
            )
            lga_mapping = render_column_mapper(
                ["lga"],
                {"lga"},
                list(etally_source.columns),
                {"lga": suggest_etally_lga(list(etally_source.columns))},
                (
                    "teams_reporting_etally_"
                    f"{st.session_state[MODULE_KEY]['input_signature']}"
                ),
            )
            default_id_columns = _suggest_team_id_columns(
                list(etally_source.columns),
                lga_mapping["lga"],
            )
            team_id_columns = st.multiselect(
                "Team ID columns (select 2 or 3)",
                list(etally_source.columns),
                default=default_id_columns,
                max_selections=3,
                key=(
                    "teams_reporting_id_"
                    f"{st.session_state[MODULE_KEY]['input_signature']}"
                ),
                help="Example: LGA + Ward + Team Number.",
            )
            etally_mapping: ETallyMapping = {
                "lga": lga_mapping["lga"],
                "team_id_columns": team_id_columns,
            }
        with distribution_tab:
            st.caption("Map the LGA and planned-team fields. Both are required.")
            distribution_mapping = render_column_mapper(
                list(DISTRIBUTION_FIELDS),
                set(DISTRIBUTION_FIELDS),
                list(distribution_source.columns),
                suggest_distribution_mapping(list(distribution_source.columns)),
                (
                    "teams_reporting_distribution_"
                    f"{st.session_state[MODULE_KEY]['input_signature']}"
                ),
            )
    return etally_mapping, distribution_mapping


def _suggest_team_id_columns(columns: list[str], lga_column: str | None) -> list[str]:
    suggested = [column for column in [lga_column] if column]
    keywords = ("ward", "team", "number", "teamno", "teamnumber")
    for column in columns:
        if column in suggested:
            continue
        normalised = "".join(
            character for character in column.lower() if character.isalnum()
        )
        if any(keyword in normalised for keyword in keywords):
            suggested.append(column)
        if len(suggested) == 3:
            break
    return suggested[:3]


def _clear_stale_results(
    etally_mapping: ETallyMapping,
    distribution_mapping: DistributionMapping,
) -> None:
    state = st.session_state[MODULE_KEY]
    mappings = (etally_mapping, distribution_mapping)
    if state["processed_mappings"] and state["processed_mappings"] != mappings:
        state["result"] = None
        state["summary"] = None
        state["processed_mappings"] = None


def _render_validation(report) -> None:
    with st.expander("3. Validation", expanded=True):
        validation_messages(report.errors, report.warnings)
        if report.is_valid:
            st.success("Both datasets are valid and ready for processing.")


def _render_results(result: pd.DataFrame, summary: TeamsReportingSummary) -> None:
    st.divider()
    st.subheader("4. Summary statistics")
    columns = st.columns(4)
    metrics = [
        ("Planned teams", f"{summary.planned_teams:,}", "From Team Distribution"),
        ("Teams reported", f"{summary.teams_reported:,}", "Distinct Team IDs"),
        ("Missing teams", f"{summary.missing_teams:,}", "Planned but not reported"),
        (
            "Reporting rate",
            _format_percent(summary.reporting_percent),
            f"Across {summary.lga_count} LGA(s)",
        ),
    ]
    for column, metric in zip(columns, metrics, strict=True):
        with column:
            kpi_card(*metric)

    st.subheader("5. Visualisations")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(reporting_rate_by_lga(result), width='stretch')
    with chart_right:
        st.plotly_chart(team_status_by_lga(result), width='stretch')

    st.subheader("6. LGA summary table")
    data_table(result)

    st.subheader("7. Download results")
    download_left, download_right = st.columns(2)
    with download_left:
        st.download_button(
            "Download LGA summary (CSV)",
            result.to_csv(index=False).encode("utf-8"),
            "teams_reporting_lga_summary.csv",
            "text/csv",
            width='stretch',
        )
    with download_right:
        st.download_button(
            "Download LGA summary (Excel)",
            _to_excel(result, summary),
            "teams_reporting_lga_summary.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
        )


def _to_excel(result: pd.DataFrame, summary: TeamsReportingSummary) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="LGA Summary", index=False)
        pd.DataFrame(
            [
                {"metric": "Planned Teams", "value": summary.planned_teams},
                {"metric": "Teams Reported", "value": summary.teams_reported},
                {"metric": "Missing Teams", "value": summary.missing_teams},
                {"metric": "Reporting Rate (%)", "value": summary.reporting_percent},
            ]
        ).to_excel(writer, sheet_name="Summary", index=False)
    return output.getvalue()


def _input_signature(etally_content: bytes, distribution_content: bytes) -> str:
    return sha256(etally_content + distribution_content).hexdigest()


def _format_percent(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "-"


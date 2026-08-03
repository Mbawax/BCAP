"""Generic upload interface shared by all future campaign modules."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

import streamlit as st

from campaign_analytics.core.storage import get_temporary_upload_directory
from campaign_analytics.components.upload import upload_data_file
from campaign_analytics.ui.components import empty_state, page_header

ALLOWED_FILE_TYPES = ["csv", "xlsx", "xls"]


def render_upload_workspace() -> None:
    """Render a safe, analysis-neutral staging area for uploaded datasets."""
    page_header(
        "Data workspace",
        "Stage campaign files here. Analysis modules will validate and process them "
        "later.",
        "Data intake",
    )
    st.info(
        "Files are staged temporarily in this foundation release. They are not yet "
        "validated, mapped, or analysed.",
        icon="ℹ️",
    )
    uploaded_files = upload_data_file(
        "Upload campaign datasets",
        key=f"campaign_uploads_{st.session_state.uploader_version}",
        help_text=(
            "Supported formats: CSV and Excel workbooks. Maximum size is configured "
            "by the platform."
        ),
        file_types=ALLOWED_FILE_TYPES,
        accept_multiple_files=True,
    )
    if uploaded_files:
        _stage_files(uploaded_files)
        st.success(f"{len(uploaded_files)} file(s) staged for this session.")
    _render_staged_files()


def _stage_files(uploaded_files: list[Any]) -> None:
    upload_directory = get_temporary_upload_directory()
    existing_names = {
        record["original_name"] for record in st.session_state.upload_records
    }
    for uploaded_file in uploaded_files:
        if uploaded_file.name in existing_names:
            continue
        stored_name = f"{uuid.uuid4().hex}_{Path(uploaded_file.name).name}"
        stored_path = upload_directory / stored_name
        stored_path.write_bytes(uploaded_file.getvalue())
        st.session_state.upload_records.append(
            {
                "id": uuid.uuid4().hex,
                "original_name": uploaded_file.name,
                "path": str(stored_path),
                "size_bytes": uploaded_file.size,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
        )


def _render_staged_files() -> None:
    records = st.session_state.upload_records
    if not records:
        empty_state(
            "No files staged",
            "Upload a CSV or Excel file to begin a future module workflow.",
            "↑",
        )
        return
    st.subheader("Staged files")
    st.dataframe(
        [
            {
                "File": record["original_name"],
                "Size (KB)": round(record["size_bytes"] / 1024, 1),
                "Staged at (UTC)": record["uploaded_at"],
            }
            for record in records
        ],
        hide_index=True,
        width='stretch',
    )
    if st.button("Clear staged files", type="secondary"):
        for record in records:
            Path(record["path"]).unlink(missing_ok=True)
        st.session_state.upload_records = []
        st.session_state.uploader_version += 1
        st.rerun()


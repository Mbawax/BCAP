"""Reusable file-upload zone for campaign data modules."""

from collections.abc import Sequence
from typing import Any

import streamlit as st


DEFAULT_FILE_TYPES = ("csv", "xlsx", "xls")


def upload_data_file(
    label: str,
    key: str,
    help_text: str,
    file_types: Sequence[str] = DEFAULT_FILE_TYPES,
    accept_multiple_files: bool = False,
) -> Any | None:
    """Render a consistent upload control and return the selected file."""
    return st.file_uploader(
        label,
        type=list(file_types),
        key=key,
        help=help_text,
        accept_multiple_files=accept_multiple_files,
    )


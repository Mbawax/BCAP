"""Reusable local readers and preview helpers for tabular campaign uploads."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st


@st.cache_data(show_spinner=False)
def read_tabular_upload(content: bytes, filename: str) -> pd.DataFrame:
    """Read a CSV or the first worksheet in an Excel workbook from upload bytes."""
    if Path(filename).suffix.lower() == ".csv":
        return pd.read_csv(BytesIO(content))
    return pd.read_excel(BytesIO(content))


def source_preview(data: pd.DataFrame, filename: str) -> None:
    """Show source dimensions and a compact data preview."""
    st.caption(
        f"{filename}: {len(data):,} rows × {len(data.columns):,} columns"
    )
    with st.expander(f"Preview: {filename}"):
        st.dataframe(data.head(20), width='stretch', hide_index=True)


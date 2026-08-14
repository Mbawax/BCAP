"""Reusable tabular data presentation helpers."""

from typing import Any
import pandas as pd
import streamlit as st


def data_table(data: Any, height: int | None = None) -> None:
    """Render a responsive, index-free DataFrame or Styler object with platform defaults."""
    kwargs: dict = {
        "hide_index": True,
        "use_container_width": True,
    }
    if height is not None:
        kwargs["height"] = height
    if isinstance(data, pd.DataFrame):
        kwargs["column_config"] = {
            column: st.column_config.Column(column) for column in data.columns
        }
    st.dataframe(data, **kwargs)

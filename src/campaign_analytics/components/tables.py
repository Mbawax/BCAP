"""Reusable tabular data presentation helpers."""

import pandas as pd
import streamlit as st


def data_table(data: pd.DataFrame, height: int | None = None) -> None:
    """Render a responsive, index-free DataFrame with platform defaults."""
    st.dataframe(
        data,
        hide_index=True,
        width='stretch',
        height=height,
        column_config={
            column: st.column_config.Column(column) for column in data.columns
        },
    )


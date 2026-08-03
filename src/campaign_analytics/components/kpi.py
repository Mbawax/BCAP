"""Reusable KPI cards for platform and campaign modules."""

from html import escape

import streamlit as st


def kpi_card(label: str, value: str, detail: str, tone: str = "teal") -> None:
    """Render a compact KPI card with an accessible explanatory detail."""
    st.markdown(
        f'<div class="kpi-card kpi-{escape(tone)}">'
        f'<div class="kpi-label">{escape(label)}</div>'
        f'<div class="kpi-value">{escape(value)}</div>'
        f'<div class="kpi-detail">{escape(detail)}</div></div>',
        unsafe_allow_html=True,
    )


"""Consistent user-facing validation and status notifications."""

from collections.abc import Sequence

import streamlit as st


def validation_messages(errors: Sequence[str], warnings: Sequence[str]) -> None:
    """Render validation errors and warnings without version-sensitive icons."""
    for message in errors:
        st.error(message)
    for message in warnings:
        st.warning(message)


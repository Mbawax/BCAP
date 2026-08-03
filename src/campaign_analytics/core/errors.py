"""User-safe error boundaries for page and module rendering."""

from collections.abc import Callable
from uuid import uuid4
import logging

import streamlit as st


def render_safely(renderer: Callable[[], None], page_name: str) -> None:
    """Render a page while logging unexpected failures with a support reference."""
    try:
        renderer()
    except Exception:
        reference = uuid4().hex[:8].upper()
        logging.getLogger("campaign_analytics").exception(
            "Unhandled error while rendering %s [reference=%s]", page_name, reference
        )
        st.error(
            "We could not load this page. Your data has not been changed. "
            f"Support reference: {reference}",
            icon="⚠️",
        )


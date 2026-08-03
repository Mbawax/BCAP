"""Streamlit entry point for the Campaign Analytics Platform."""

from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from campaign_analytics.core.registry import discover_modules
from campaign_analytics.core.errors import render_safely
from campaign_analytics.core.logging import configure_logging
from campaign_analytics.core.session import initialise_session
from campaign_analytics.ui.app_shell import render_app_shell


def main() -> None:
    """Configure and render the application shell."""
    st.set_page_config(
        page_title="Campaign Analytics",
        page_icon="✚",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialise_session()
    configure_logging(ROOT)
    render_safely(_render_application, "Application")


def _render_application() -> None:
    """Discover registered modules and render the application safely."""
    registry = discover_modules(ROOT / "src" / "campaign_analytics" / "modules")
    render_app_shell(registry)


if __name__ == "__main__":
    main()

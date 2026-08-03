"""Module entry point used by the platform registry."""

from campaign_analytics.modules.vaccination.ui import render_vaccination_module


def render() -> None:
    """Render the independent Vaccination Analysis module."""
    render_vaccination_module()


"""Module entry point used by the platform registry for Settlement Analysis."""

from campaign_analytics.modules.settlement_analysis.ui import render_settlement_analysis_module


def render() -> None:
    """Render the independent Settlement Analysis module."""
    render_settlement_analysis_module()

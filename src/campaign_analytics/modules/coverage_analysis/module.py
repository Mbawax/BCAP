"""Module entry point used by the platform registry for Coverage Analysis."""

from campaign_analytics.modules.coverage_analysis.ui import render_coverage_analysis_module


def render() -> None:
    """Render the independent Coverage Analysis module."""
    render_coverage_analysis_module()

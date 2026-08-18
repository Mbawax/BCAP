"""Module entry point used by the platform registry for LGA Coverage Analysis."""

from campaign_analytics.modules.lga_coverage_analysis.ui import render_lga_coverage_analysis_module


def render() -> None:
    """Render the LGA Coverage Analysis module."""
    render_lga_coverage_analysis_module()

"""Module entry point used by the platform registry for Ward Coverage Analysis."""

from campaign_analytics.modules.ward_coverage_analysis.ui import render_ward_coverage_analysis_module


def render() -> None:
    """Render the Ward Coverage Analysis module."""
    render_ward_coverage_analysis_module()

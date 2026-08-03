"""Module entry point used by the platform registry."""

from campaign_analytics.modules.teams_reporting.ui import render_teams_reporting_module


def render() -> None:
    """Render the independent Teams Reporting module."""
    render_teams_reporting_module()


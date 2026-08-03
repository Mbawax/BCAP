"""Validation entry point for Teams Reporting."""

from campaign_analytics.modules.teams_reporting.processor import (
    ValidationReport,
    validate_inputs,
)

__all__ = ["ValidationReport", "validate_inputs"]


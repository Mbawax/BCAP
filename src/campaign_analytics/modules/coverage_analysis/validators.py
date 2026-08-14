"""Validation entry point for Coverage Analysis."""

from campaign_analytics.modules.coverage_analysis.processor import (
    ValidationReport,
    validate_inputs,
)

__all__ = ["ValidationReport", "validate_inputs"]

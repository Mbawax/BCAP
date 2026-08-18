"""Validation entry point for Ward Coverage Analysis."""

from campaign_analytics.modules.ward_coverage_analysis.processor import (
    ValidationReport,
    validate_ward_inputs,
)

__all__ = ["ValidationReport", "validate_ward_inputs"]

"""Validation entry point for LGA Coverage Analysis."""

from campaign_analytics.modules.lga_coverage_analysis.processor import (
    ValidationReport,
    validate_lga_inputs,
)

__all__ = ["ValidationReport", "validate_lga_inputs"]

"""Validation entry point for Settlement Analysis."""

from campaign_analytics.modules.settlement_analysis.processor import (
    ValidationReport,
    validate_inputs,
)

__all__ = ["ValidationReport", "validate_inputs"]

"""Validation entry point for the Vaccination Analysis module."""

from campaign_analytics.modules.vaccination.processor import (
    ValidationReport,
    validate_inputs,
)

__all__ = ["ValidationReport", "validate_inputs"]


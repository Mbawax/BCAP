"""Tests for the pure, independent nOPV and bOPV coverage processor.

All tests run without Streamlit and verify the processor's data contracts,
validation logic, and edge-case handling.
"""

import pandas as pd
import pytest

from campaign_analytics.modules.vaccination.processor import (
    SUMMARY_COLUMNS,
    ValidationReport,
    process_all_vaccines,
    validate_inputs,
)

# ── Shared test fixtures ──────────────────────────────────────────────────────

_TARGET_MAPPING = {"lga": "LGA", "target_population": "Target"}
_ETALLY_MAPPING = {
    "lga": "LGA",
    "nopv_vaccinated": "nOPV",
    "bopv_vaccinated": "bOPV",
}


def _make_target(lgas: list[str], targets: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"LGA": lgas, "Target": targets})


def _make_etally(
    lgas: list[str], nopv: list[int], bopv: list[int],
) -> pd.DataFrame:
    return pd.DataFrame({"LGA": lgas, "nOPV": nopv, "bOPV": bopv})


# ── Processing tests ──────────────────────────────────────────────────────────

class TestProcessAllVaccines:
    """Core processing logic."""

    def test_independent_nopv_and_bopv_analyses(self) -> None:
        """nOPV and bOPV must never share intermediate calculations."""
        target = _make_target(["Bama", "Maiduguri"], [100, 200])
        etally = _make_etally(
            ["BAMA", "Maiduguri", "Maiduguri"], [60, 80, 40], [50, 90, 30],
        )
        analyses = process_all_vaccines(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )

        assert analyses["nopv"].summary.vaccinated == 180
        assert analyses["nopv"].summary.coverage_percent == 60.0
        assert analyses["bopv"].summary.vaccinated == 170
        assert analyses["bopv"].summary.coverage_percent == 56.7

    def test_output_has_human_readable_column_names(self) -> None:
        """The LGA summary table must use presentation-ready headers."""
        target = _make_target(["Bama"], [100])
        etally = _make_etally(["Bama"], [60], [50])
        analyses = process_all_vaccines(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert list(analyses["nopv"].lga_summary.columns) == SUMMARY_COLUMNS
        assert list(analyses["bopv"].lga_summary.columns) == SUMMARY_COLUMNS

    def test_duplicate_lgas_are_aggregated(self) -> None:
        """Multiple rows for the same LGA must be summed, not duplicated."""
        target = _make_target(["Bama", "BAMA"], [100, 50])
        etally = _make_etally(["Bama"], [80], [60])
        analyses = process_all_vaccines(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert len(analyses["nopv"].lga_summary) == 1
        assert analyses["nopv"].summary.target_population == 150
        assert analyses["nopv"].summary.vaccinated == 80

    def test_zero_target_produces_none_coverage(self) -> None:
        """Division by zero must not raise — coverage should be NaN/None."""
        target = _make_target(["EmptyLGA"], [0])
        etally = _make_etally(["EmptyLGA"], [10], [5])
        analyses = process_all_vaccines(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        row = analyses["nopv"].lga_summary.iloc[0]
        assert pd.isna(row["Coverage (%)"])
        # Overall summary should also handle zero denominator
        assert analyses["nopv"].summary.coverage_percent is None

    def test_remaining_never_negative(self) -> None:
        """If vaccinated > target, remaining must clip to zero."""
        target = _make_target(["Bama"], [50])
        etally = _make_etally(["Bama"], [100], [80])
        analyses = process_all_vaccines(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert analyses["nopv"].lga_summary.iloc[0]["Remaining"] == 0
        assert analyses["nopv"].summary.remaining == 0

    def test_missing_values_coerced_to_zero(self) -> None:
        """Blank or non-numeric vaccinated values must be treated as zero."""
        target = _make_target(["Bama"], [100])
        etally = pd.DataFrame({
            "LGA": ["Bama"], "nOPV": [None], "bOPV": ["N/A"],
        })
        analyses = process_all_vaccines(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert analyses["nopv"].summary.vaccinated == 0
        assert analyses["bopv"].summary.vaccinated == 0

    def test_unmatched_etally_lga_excluded(self) -> None:
        """eTally LGAs without a target match do not appear in the result."""
        target = _make_target(["Bama"], [100])
        etally = _make_etally(["Bama", "Unknown"], [60, 30], [50, 20])
        analyses = process_all_vaccines(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert len(analyses["nopv"].lga_summary) == 1
        assert analyses["nopv"].summary.vaccinated == 60


# ── Validation tests ──────────────────────────────────────────────────────────

class TestValidation:
    """Input validation before processing."""

    def test_valid_inputs_pass(self) -> None:
        target = _make_target(["Bama"], [100])
        etally = _make_etally(["Bama"], [60], [50])
        report = validate_inputs(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert report.is_valid
        assert not report.errors

    def test_warns_when_etally_lga_has_no_target_match(self) -> None:
        target = _make_target(["Bama"], [100])
        etally = _make_etally(["Other"], [5], [4])
        report = validate_inputs(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert report.is_valid
        assert "no target-population match" in report.warnings[0]

    def test_warns_on_duplicate_target_lgas(self) -> None:
        target = _make_target(["Bama", "Bama"], [100, 50])
        etally = _make_etally(["Bama"], [60], [50])
        report = validate_inputs(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert report.is_valid
        assert any("duplicate" in w.lower() for w in report.warnings)

    def test_warns_on_zero_target_population(self) -> None:
        target = _make_target(["Bama"], [0])
        etally = _make_etally(["Bama"], [60], [50])
        report = validate_inputs(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert report.is_valid
        assert any("zero" in w.lower() for w in report.warnings)

    def test_errors_on_negative_values(self) -> None:
        target = _make_target(["Bama"], [100])
        etally = pd.DataFrame({
            "LGA": ["Bama"], "nOPV": [-5], "bOPV": [50],
        })
        report = validate_inputs(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert not report.is_valid
        assert any("negative" in e.lower() for e in report.errors)

    def test_errors_on_unmapped_required_field(self) -> None:
        target = _make_target(["Bama"], [100])
        etally = _make_etally(["Bama"], [60], [50])
        bad_mapping = {"lga": "LGA", "target_population": None}
        report = validate_inputs(
            target, etally, bad_mapping, _ETALLY_MAPPING,
        )
        assert not report.is_valid
        assert any("map the required field" in e.lower() for e in report.errors)

    def test_errors_on_blank_lga_values(self) -> None:
        target = pd.DataFrame({"LGA": ["Bama", ""], "Target": [100, 50]})
        etally = _make_etally(["Bama"], [60], [50])
        report = validate_inputs(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert not report.is_valid
        assert any("blank lga" in e.lower() for e in report.errors)

    def test_warns_on_non_numeric_values(self) -> None:
        target = _make_target(["Bama"], [100])
        etally = pd.DataFrame({
            "LGA": ["Bama"], "nOPV": ["abc"], "bOPV": [50],
        })
        report = validate_inputs(
            target, etally, _TARGET_MAPPING, _ETALLY_MAPPING,
        )
        assert report.is_valid
        assert any("non-numeric" in w.lower() for w in report.warnings)

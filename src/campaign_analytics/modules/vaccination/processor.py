"""Pure two-source processing for independent vaccine coverage analyses.

All public functions are free of Streamlit imports so they can be unit-tested
without a running Streamlit server.  Each vaccine is processed independently —
nOPV and bOPV never share intermediate calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

import pandas as pd

Mapping: TypeAlias = dict[str, str | None]

# Canonical field identifiers used by the column mapper.
TARGET_FIELDS = ("lga", "target_population")
ETALLY_FIELDS = ("lga", "nopv_vaccinated", "bopv_vaccinated")

# Human-readable column names for the output LGA summary table.
_COL_LGA = "LGA"
_COL_TARGET = "Target Population"
_COL_VACCINATED = "Vaccinated"
_COL_REMAINING = "Remaining"
_COL_COVERAGE = "Coverage (%)"

SUMMARY_COLUMNS = [_COL_LGA, _COL_TARGET, _COL_VACCINATED, _COL_REMAINING, _COL_COVERAGE]


# ── Data contracts ────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class VaccineDefinition:
    """Describes one vaccine output without coupling it to UI implementation."""

    code: str
    label: str
    etally_field: str


VACCINES = (
    VaccineDefinition("nopv", "nOPV", "nopv_vaccinated"),
    VaccineDefinition("bopv", "bOPV", "bopv_vaccinated"),
)


@dataclass(slots=True)
class ValidationReport:
    """Validation outcome for the two source datasets and their mappings."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return whether processing can proceed."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class VaccineSummary:
    """KPIs for one vaccine analysis only."""

    target_population: int
    vaccinated: int
    remaining: int
    coverage_percent: float | None
    lga_count: int


@dataclass(frozen=True, slots=True)
class VaccineAnalysis:
    """An individual vaccine summary paired with its LGA-level result table."""

    definition: VaccineDefinition
    summary: VaccineSummary
    lga_summary: pd.DataFrame


# ── Column suggestion helpers ─────────────────────────────────────────────────

def suggest_target_mapping(columns: list[str]) -> Mapping:
    """Suggest LGA and target-population columns from common source labels."""
    return _suggest_mapping(
        columns,
        {
            "lga": ("lga", "localgovernmentarea", "district"),
            "target_population": (
                "targetpopulation",
                "totalpopulation",
                "target",
                "populationtarget",
                "eligiblechildren",
                "targetchildren",
            ),
        },
    )


def suggest_etally_mapping(columns: list[str]) -> Mapping:
    """Suggest eTally LGA, nOPV, and bOPV vaccination columns."""
    return _suggest_mapping(
        columns,
        {
            "lga": ("lga", "lgas", "localgovernmentarea", "district"),
            "nopv_vaccinated": (
                "nopvvaccinated",
                "nopv",
                "totalnopv",
                "nopvdoses",
            ),
            "bopv_vaccinated": (
                "bopvvaccinated",
                "bopv",
                "totalbopv",
                "bopvdoses",
            ),
        },
    )


# ── Validation ────────────────────────────────────────────────────────────────

def validate_inputs(
    target_source: pd.DataFrame,
    etally_source: pd.DataFrame,
    target_mapping: Mapping,
    etally_mapping: Mapping,
) -> ValidationReport:
    """Validate source mappings and values before any coverage calculation."""
    report = ValidationReport()

    # Required mapping checks
    _validate_mapping(
        target_source, target_mapping, TARGET_FIELDS, "Target Population", report,
    )
    _validate_mapping(
        etally_source, etally_mapping, ETALLY_FIELDS, "eTally", report,
    )
    if report.errors:
        return report

    # Numeric column checks
    _validate_numeric_column(
        target_source, target_mapping["target_population"], "Target Population", report,
    )
    for vaccine in VACCINES:
        _validate_numeric_column(
            etally_source,
            etally_mapping[vaccine.etally_field],
            f"eTally {vaccine.label}",
            report,
        )

    # LGA integrity checks
    target_lga_col = target_mapping["lga"]
    etally_lga_col = etally_mapping["lga"]
    target_lgas = _normalise_lga(target_source[target_lga_col])
    etally_lgas = _normalise_lga(etally_source[etally_lga_col])

    if target_lgas.isna().any():
        blank_count = int(target_lgas.isna().sum())
        report.errors.append(
            f"Target Population contains {blank_count:,} blank LGA value(s). "
            "Please remove or fill blank rows."
        )
    if etally_lgas.isna().any():
        blank_count = int(etally_lgas.isna().sum())
        report.errors.append(
            f"eTally contains {blank_count:,} blank LGA value(s). "
            "Please remove or fill blank rows."
        )

    # Duplicate LGA warnings
    target_dupes = target_lgas.dropna()
    dupe_count = int(target_dupes.duplicated().sum())
    if dupe_count:
        report.warnings.append(
            f"Target Population has {dupe_count:,} duplicate LGA row(s). "
            "Values will be aggregated (summed) per LGA."
        )

    # Zero-target warnings
    if target_mapping["target_population"]:
        numeric_target = _coerce_numeric(target_source[target_mapping["target_population"]])
        zero_count = int((numeric_target.fillna(0) == 0).sum())
        if zero_count:
            report.warnings.append(
                f"Target Population has {zero_count:,} row(s) with a zero or blank "
                "target. Coverage will show as '–' for those LGAs."
            )

    # Cross-dataset match
    target_set = set(target_lgas.dropna())
    etally_set = set(etally_lgas.dropna())
    unmatched = etally_set - target_set
    if unmatched:
        report.warnings.append(
            f"{len(unmatched)} eTally LGA(s) have no target-population match and "
            "will be excluded from coverage calculations."
        )

    return report


# ── Processing ────────────────────────────────────────────────────────────────

def process_all_vaccines(
    target_source: pd.DataFrame,
    etally_source: pd.DataFrame,
    target_mapping: Mapping,
    etally_mapping: Mapping,
    vaccines: tuple[VaccineDefinition, ...] = VACCINES,
) -> dict[str, VaccineAnalysis]:
    """Process each vaccine independently against the same mapped target dataset."""
    target_by_lga = _prepare_target(target_source, target_mapping)
    return {
        vaccine.code: _process_single_vaccine(
            target_by_lga, etally_source, etally_mapping, vaccine,
        )
        for vaccine in vaccines
    }


def _process_single_vaccine(
    target_by_lga: pd.DataFrame,
    etally_source: pd.DataFrame,
    etally_mapping: Mapping,
    vaccine: VaccineDefinition,
) -> VaccineAnalysis:
    """Produce one vaccine result without combining it with any other vaccine."""
    vaccinated_by_lga = _prepare_etally(etally_source, etally_mapping, vaccine)

    result = (
        target_by_lga
        .merge(vaccinated_by_lga, on="lga_key", how="left")
        .assign(
            **{
                _COL_VACCINATED: lambda df: df[_COL_VACCINATED].fillna(0).astype(int),
                _COL_REMAINING: lambda df: (
                    df[_COL_TARGET] - df[_COL_VACCINATED].fillna(0)
                ).clip(lower=0).astype(int),
                _COL_COVERAGE: lambda df: (
                    df[_COL_VACCINATED].fillna(0)
                    / df[_COL_TARGET].where(df[_COL_TARGET] > 0)
                    * 100
                ).round(1),
            }
        )
        .loc[:, SUMMARY_COLUMNS]
        .sort_values(_COL_LGA)
        .reset_index(drop=True)
    )

    total_target = int(result[_COL_TARGET].sum())
    total_vaccinated = int(result[_COL_VACCINATED].sum())
    summary = VaccineSummary(
        target_population=total_target,
        vaccinated=total_vaccinated,
        remaining=max(total_target - total_vaccinated, 0),
        coverage_percent=_safe_percentage(total_vaccinated, total_target),
        lga_count=len(result),
    )
    return VaccineAnalysis(vaccine, summary, result)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _prepare_target(source: pd.DataFrame, mapping: Mapping) -> pd.DataFrame:
    """Aggregate target population by normalised LGA key."""
    target = pd.DataFrame({
        _COL_LGA: _clean_lga(source[mapping["lga"]]),
        _COL_TARGET: _coerce_numeric(source[mapping["target_population"]]).fillna(0).astype(int),
    })
    target["lga_key"] = _normalise_lga(target[_COL_LGA])
    return (
        target
        .groupby("lga_key", as_index=False)
        .agg(**{_COL_LGA: (_COL_LGA, "first"), _COL_TARGET: (_COL_TARGET, "sum")})
        .sort_values(_COL_LGA)
    )


def _prepare_etally(
    source: pd.DataFrame,
    mapping: Mapping,
    vaccine: VaccineDefinition,
) -> pd.DataFrame:
    """Aggregate vaccinated counts by normalised LGA key for one vaccine."""
    etally = pd.DataFrame({
        "lga_key": _normalise_lga(source[mapping["lga"]]),
        _COL_VACCINATED: _coerce_numeric(source[mapping[vaccine.etally_field]]).fillna(0).astype(int),
    })
    return etally.groupby("lga_key", as_index=False)[_COL_VACCINATED].sum()


def _validate_mapping(
    source: pd.DataFrame,
    mapping: Mapping,
    fields: tuple[str, ...],
    dataset_name: str,
    report: ValidationReport,
) -> None:
    """Verify that every required field has a unique, existing source column."""
    selected = [mapping.get(f) for f in fields if mapping.get(f)]
    duplicates = sorted({col for col in selected if selected.count(col) > 1})
    if duplicates:
        report.errors.append(
            f"{dataset_name}: each field needs a different source column. "
            f"Duplicate: {', '.join(duplicates)}."
        )
    for fld in fields:
        column = mapping.get(fld)
        if not column:
            report.errors.append(
                f"{dataset_name}: please map the required field "
                f"'{fld.replace('_', ' ').title()}'."
            )
        elif column not in source.columns:
            report.errors.append(
                f"{dataset_name}: mapped column '{column}' was not found in the file."
            )


def _validate_numeric_column(
    source: pd.DataFrame,
    column: str | None,
    label: str,
    report: ValidationReport,
) -> None:
    """Check a numeric column for blanks and negative values."""
    if column is None:
        return
    numeric = _coerce_numeric(source[column])
    invalid = int(numeric.isna().sum())
    negative = int((numeric.dropna() < 0).sum())
    if invalid:
        report.warnings.append(
            f"{label}: {invalid:,} blank or non-numeric value(s) will be treated "
            "as zero."
        )
    if negative:
        report.errors.append(
            f"{label}: {negative:,} negative value(s) found. "
            "All values must be zero or positive."
        )


def _suggest_mapping(
    columns: list[str], aliases: dict[str, tuple[str, ...]]
) -> Mapping:
    """Auto-suggest column mappings from a dictionary of normalised aliases."""
    normalised = {_normalise_name(col): col for col in columns}
    return {
        field: next((normalised[name] for name in names if name in normalised), None)
        for field, names in aliases.items()
    }


def _normalise_name(name: str) -> str:
    """Normalise a column header to lowercase alphanumeric for matching."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _clean_lga(values: pd.Series) -> pd.Series:
    """Strip whitespace and convert empty strings to NA."""
    return values.astype("string").str.strip().replace({"": pd.NA})


def _normalise_lga(values: pd.Series) -> pd.Series:
    """Casefolded, whitespace-normalised LGA for join keys."""
    return _clean_lga(values).str.casefold().str.replace(r"\s+", " ", regex=True)


def _coerce_numeric(values: pd.Series) -> pd.Series:
    """Coerce a column to numeric, stripping commas and whitespace."""
    cleaned = values.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce")


def _safe_percentage(numerator: int, denominator: int) -> float | None:
    """Return a rounded percentage or None when division is impossible."""
    return round(numerator / denominator * 100, 1) if denominator > 0 else None

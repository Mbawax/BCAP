"""Pure processing for planned-versus-reported campaign team analysis."""

from dataclasses import dataclass, field
from typing import TypeAlias

import pandas as pd

DistributionMapping: TypeAlias = dict[str, str | None]
ETallyMapping: TypeAlias = dict[str, object]

DISTRIBUTION_FIELDS = ("lga", "planned_teams")


@dataclass(slots=True)
class ValidationReport:
    """Validation outcome for eTally and Team Distribution inputs."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return whether all required data is suitable for processing."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class TeamsReportingSummary:
    """Campaign-level KPIs for team reporting."""

    planned_teams: int
    teams_reported: int
    missing_teams: int
    reporting_percent: float | None
    lga_count: int


def suggest_distribution_mapping(columns: list[str]) -> DistributionMapping:
    """Suggest Team Distribution mappings from common campaign column names."""
    normalised = {_normalise_name(column): column for column in columns}
    aliases = {
        "lga": ("lga", "localgovernmentarea", "district"),
        "planned_teams": (
            "plannedteams",
            "teamsplanned",
            "totalplannedteams",
            "numberofplannedteams",
            "planned",
        ),
    }
    return {
        field: next((normalised[name] for name in names if name in normalised), None)
        for field, names in aliases.items()
    }


def suggest_etally_lga(columns: list[str]) -> str | None:
    """Suggest an eTally LGA column from typical source labels."""
    normalised = {_normalise_name(column): column for column in columns}
    return next(
        (
            normalised[name]
            for name in ("lga", "localgovernmentarea", "district")
            if name in normalised
        ),
        None,
    )


def validate_inputs(
    etally_source: pd.DataFrame,
    distribution_source: pd.DataFrame,
    etally_mapping: ETallyMapping,
    distribution_mapping: DistributionMapping,
) -> ValidationReport:
    """Validate LGA mappings, ID components, and planned-team values."""
    report = ValidationReport()
    _validate_distribution_mapping(distribution_source, distribution_mapping, report)
    _validate_etally_mapping(etally_source, etally_mapping, report)
    if report.errors:
        return report

    planned_column = distribution_mapping["planned_teams"]
    numeric_planned = _coerce_numeric(distribution_source[planned_column])
    invalid_planned = int(numeric_planned.isna().sum())
    negative_planned = int((numeric_planned.dropna() < 0).sum())
    if invalid_planned:
        report.warnings.append(
            f"Team Distribution: {invalid_planned:,} blank or non-numeric planned "
            "team value(s) will be treated as zero."
        )
    if negative_planned:
        report.errors.append(
            "Team Distribution: negative planned-team values are not allowed."
        )

    team_columns = _team_id_columns(etally_mapping)
    incomplete_ids = int(
        _team_id_parts(etally_source, team_columns).isna().any(axis=1).sum()
    )
    if incomplete_ids:
        report.warnings.append(
            f"eTally: {incomplete_ids:,} row(s) have incomplete Team ID components "
            "and will not be counted as reported teams."
        )

    distribution_lgas = set(
        _normalise_lga(distribution_source[distribution_mapping["lga"]]).dropna()
    )
    etally_lgas = set(_normalise_lga(etally_source[etally_mapping["lga"]]).dropna())
    unmatched = etally_lgas - distribution_lgas
    if unmatched:
        report.warnings.append(
            f"{len(unmatched)} eTally LGA(s) have no Team Distribution match and "
            "will be excluded from LGA reporting calculations."
        )
    return report


def process_data(
    etally_source: pd.DataFrame,
    distribution_source: pd.DataFrame,
    etally_mapping: ETallyMapping,
    distribution_mapping: DistributionMapping,
) -> tuple[pd.DataFrame, TeamsReportingSummary]:
    """Count unique reported teams and compare them with LGA planned teams."""
    distribution_by_lga = _prepare_distribution(
        distribution_source,
        distribution_mapping,
    )
    reported_by_lga = _prepare_reported_teams(etally_source, etally_mapping)
    result = distribution_by_lga.merge(reported_by_lga, on="lga_key", how="left")
    result["teams_reported"] = result["teams_reported"].fillna(0).astype(int)
    result["missing_teams"] = (
        result["planned_teams"] - result["teams_reported"]
    ).clip(lower=0)
    result["reporting_percent"] = (
        result["teams_reported"]
        / result["planned_teams"].where(result["planned_teams"] > 0)
        * 100
    ).round(1)
    result = result.loc[
        :,
        [
            "lga",
            "planned_teams",
            "teams_reported",
            "missing_teams",
            "reporting_percent",
        ],
    ].sort_values("lga")

    planned = int(result["planned_teams"].sum())
    reported = int(result["teams_reported"].sum())
    summary = TeamsReportingSummary(
        planned_teams=planned,
        teams_reported=reported,
        missing_teams=max(planned - reported, 0),
        reporting_percent=_percentage(reported, planned),
        lga_count=len(result),
    )
    return result, summary


def _validate_distribution_mapping(
    source: pd.DataFrame,
    mapping: DistributionMapping,
    report: ValidationReport,
) -> None:
    selected = [
        mapping.get(field) for field in DISTRIBUTION_FIELDS if mapping.get(field)
    ]
    if len(set(selected)) != len(selected):
        report.errors.append(
            "Team Distribution: LGA and Planned Teams must use different columns."
        )
    for field in DISTRIBUTION_FIELDS:
        column = mapping.get(field)
        if not column:
            report.errors.append(
                f"Team Distribution: map the required field '{field}'."
            )
        elif column not in source.columns:
            report.errors.append(
                f"Team Distribution: mapped column '{column}' was not found."
            )


def _validate_etally_mapping(
    source: pd.DataFrame,
    mapping: ETallyMapping,
    report: ValidationReport,
) -> None:
    lga_column = mapping.get("lga")
    team_columns = _team_id_columns(mapping)
    if not isinstance(lga_column, str) or lga_column not in source.columns:
        report.errors.append("eTally: map the required LGA column.")
    if len(team_columns) not in (2, 3):
        report.errors.append(
            "eTally: select exactly two or three columns to construct a Team ID."
        )
    elif len(set(team_columns)) != len(team_columns):
        report.errors.append("eTally: Team ID columns must be unique.")
    elif any(column not in source.columns for column in team_columns):
        report.errors.append(
            "eTally: one or more selected Team ID columns were not found."
        )
    elif lga_column not in team_columns:
        report.errors.append(
            "eTally: include the mapped LGA column in the Team ID columns."
        )


def _prepare_distribution(
    source: pd.DataFrame,
    mapping: DistributionMapping,
) -> pd.DataFrame:
    distribution = pd.DataFrame(
        {
            "lga": _clean_lga(source[mapping["lga"]]),
            "planned_teams": _coerce_numeric(
                source[mapping["planned_teams"]]
            ).fillna(0),
        }
    )
    distribution["lga_key"] = _normalise_lga(distribution["lga"])
    return (
        distribution.groupby("lga_key", as_index=False)
        .agg(lga=("lga", "first"), planned_teams=("planned_teams", "sum"))
        .sort_values("lga")
    )


def _prepare_reported_teams(
    source: pd.DataFrame,
    mapping: ETallyMapping,
) -> pd.DataFrame:
    team_columns = _team_id_columns(mapping)
    report = pd.DataFrame({"lga_key": _normalise_lga(source[mapping["lga"]])})
    id_parts = _team_id_parts(source, team_columns)
    valid_rows = id_parts.notna().all(axis=1) & report["lga_key"].notna()
    report["team_id"] = id_parts.fillna("").agg(" | ".join, axis=1)
    return (
        report.loc[valid_rows]
        .groupby("lga_key", as_index=False)["team_id"]
        .nunique()
        .rename(columns={"team_id": "teams_reported"})
    )


def _team_id_columns(mapping: ETallyMapping) -> list[str]:
    columns = mapping.get("team_id_columns", [])
    if not isinstance(columns, list):
        return []
    return [column for column in columns if isinstance(column, str)]


def _team_id_parts(source: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Normalise Team ID components and treat blank values as incomplete."""
    return source[columns].astype("string").apply(
        lambda values: values.str.strip().str.casefold().replace({"": pd.NA})
    )


def _normalise_name(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def _clean_lga(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().replace({"": pd.NA})


def _normalise_lga(values: pd.Series) -> pd.Series:
    return _clean_lga(values).str.casefold().str.replace(r"\s+", " ", regex=True)


def _coerce_numeric(values: pd.Series) -> pd.Series:
    cleaned = values.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce")


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator > 0 else None


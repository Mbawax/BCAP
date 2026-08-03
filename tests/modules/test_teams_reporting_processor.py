"""Tests for unique Team ID construction and LGA reporting calculations."""

import pandas as pd

from campaign_analytics.modules.teams_reporting.processor import (
    process_data,
    validate_inputs,
)


def test_counts_distinct_team_ids_from_three_source_columns() -> None:
    etally = pd.DataFrame(
        {
            "LGA": ["Bama", "Bama", "Bama", "Maiduguri"],
            "Ward": ["A", "A", "A", "B"],
            "Team Number": [1, 1, 2, 1],
        }
    )
    distribution = pd.DataFrame(
        {"LGA": ["Bama", "Maiduguri"], "Planned": [3, 2]}
    )
    etally_mapping = {
        "lga": "LGA",
        "team_id_columns": ["LGA", "Ward", "Team Number"],
    }
    distribution_mapping = {"lga": "LGA", "planned_teams": "Planned"}

    result, summary = process_data(
        etally,
        distribution,
        etally_mapping,
        distribution_mapping,
    )

    assert summary.planned_teams == 5
    assert summary.teams_reported == 3
    assert summary.missing_teams == 2
    assert summary.reporting_percent == 60.0
    assert result.loc[result["lga"] == "Bama", "teams_reported"].item() == 2


def test_validation_requires_lga_to_be_part_of_team_id() -> None:
    etally = pd.DataFrame({"LGA": ["Bama"], "Ward": ["A"], "Team": [1]})
    distribution = pd.DataFrame({"LGA": ["Bama"], "Planned": [1]})
    etally_mapping = {"lga": "LGA", "team_id_columns": ["Ward", "Team"]}
    distribution_mapping = {"lga": "LGA", "planned_teams": "Planned"}

    report = validate_inputs(
        etally,
        distribution,
        etally_mapping,
        distribution_mapping,
    )

    assert not report.is_valid
    assert "include the mapped LGA" in report.errors[0]

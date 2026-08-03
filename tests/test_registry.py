"""Tests for the manifest-driven module registry."""

from pathlib import Path

from campaign_analytics.core.registry import discover_modules


def test_discovery_returns_empty_list_when_module_folder_is_missing(tmp_path: Path) -> None:
    assert discover_modules(tmp_path / "modules") == []

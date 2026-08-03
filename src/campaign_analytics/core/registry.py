"""Discovery of future campaign modules from declarative manifests."""

from collections import defaultdict
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import toml

from campaign_analytics.core.contracts import ModuleManifest


class ModuleRegistryError(ValueError):
    """Raised when a module manifest is malformed or duplicated."""


def discover_modules(modules_root: Path) -> list[ModuleManifest]:
    """Load every valid `module.toml` below the supplied modules directory.

    A future module becomes visible by adding only its folder and manifest. Invalid
    manifests fail clearly during development rather than yielding a broken route.
    """
    if not modules_root.exists():
        return []

    discovered: list[ModuleManifest] = []
    identifiers: set[str] = set()
    for manifest_path in modules_root.glob("*/module.toml"):
        manifest = _read_manifest(manifest_path)
        if manifest.identifier in identifiers:
            raise ModuleRegistryError(
                f"Duplicate module identifier: {manifest.identifier!r}."
            )
        identifiers.add(manifest.identifier)
        discovered.append(manifest)
    return sorted(discovered, key=lambda item: (item.group, item.order, item.name))


def group_modules(registry: list[ModuleManifest]) -> dict[str, list[ModuleManifest]]:
    """Return the registry grouped for sidebar rendering."""
    grouped: dict[str, list[ModuleManifest]] = defaultdict(list)
    for manifest in registry:
        grouped[manifest.group].append(manifest)
    return dict(grouped)


def _read_manifest(manifest_path: Path) -> ModuleManifest:
    try:
        with manifest_path.open("rb") as manifest_file:
            data = tomllib.load(manifest_file)
    except NameError:
        with manifest_path.open("r", encoding="utf-8") as manifest_file:
            data = toml.load(manifest_file)
    required = ("id", "name", "group", "icon", "order", "status")
    missing = [key for key in required if key not in data]
    if missing:
        raise ModuleRegistryError(
            f"{manifest_path}: missing required field(s): {', '.join(missing)}."
        )
    return ModuleManifest(
        identifier=str(data["id"]),
        name=str(data["name"]),
        group=str(data["group"]),
        icon=str(data["icon"]),
        order=int(data["order"]),
        status=str(data["status"]),
        entry_point=data.get("entry_point"),
        path=manifest_path.parent,
    )


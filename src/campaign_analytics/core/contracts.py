"""Stable contracts shared between the shell and future modules."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Declarative metadata required for sidebar module discovery."""

    identifier: str
    name: str
    group: str
    icon: str
    order: int
    status: str
    entry_point: str | None
    path: Path

    @property
    def is_available(self) -> bool:
        """Return whether the module can be opened by the application."""
        return self.status == "active" and bool(self.entry_point)


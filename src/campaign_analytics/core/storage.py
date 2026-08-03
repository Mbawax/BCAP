"""Local-development storage paths for the shared upload framework."""

from pathlib import Path
import tempfile


def get_temporary_upload_directory() -> Path:
    """Return an application-scoped temporary location for transient uploads."""
    directory = Path(tempfile.gettempdir()) / "campaign_analytics_uploads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


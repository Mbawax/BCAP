"""Application logging configured once for the Streamlit process."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(project_root: Path) -> logging.Logger:
    """Configure a rotating application log without duplicating handlers."""
    logger = logging.getLogger("campaign_analytics")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    log_directory = project_root / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_directory / "campaign_analytics.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    return logger


"""Logging of ValutaTrade Hub: records go to rotating files in logs/."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

ACTIONS_LOGGER = "valutatrade.actions"
PARSER_LOGGER = "valutatrade.parser"


def setup_logging() -> None:
    """Send trade and parser events to separate rotating files."""
    settings = SettingsLoader()
    _add_rotating_file(ACTIONS_LOGGER, settings.log_path("actions_log_file"))
    _add_rotating_file(PARSER_LOGGER, settings.log_path("parser_log_file"))


def _add_rotating_file(name: str, path: Path) -> None:
    """Send the records of a logger to a file that rotates by size."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return
    settings = SettingsLoader()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backup_count"),
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        settings.get("log_format"), settings.get("log_date_format")
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(settings.get("log_level"))
    logger.propagate = False

"""Project settings: defaults in code, overrides from pyproject.toml."""

import tomllib
from pathlib import Path
from typing import Any, Self

PYPROJECT_FILE = Path("pyproject.toml")
SETTINGS_SECTION = "valutatrade"
DEFAULTS: dict[str, Any] = {
    "data_dir": "data",
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "rates_history_file": "exchange_rates.json",
    "rates_ttl_seconds": 300,
    "quote_cache_seconds": 60,
    "default_base_currency": "USD",
    "logs_dir": "logs",
    "actions_log_file": "actions.log",
    "log_level": "INFO",
    "log_format": "%(levelname)s %(asctime)s %(message)s",
    "log_date_format": "%Y-%m-%dT%H:%M:%S",
    "log_max_bytes": 1_000_000,
    "log_backup_count": 3,
}


class SettingsLoader:
    """The configuration of the application; there is exactly one instance.

    The singleton is built with __new__: it is the shortest and most readable
    way, while a metaclass would need a second class for the same result.
    """

    _instance: "SettingsLoader | None" = None

    def __new__(cls) -> Self:
        """Return the only instance; create and load it on the first call."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reload()
        return cls._instance

    def reload(self) -> None:
        """Take the defaults and apply [tool.valutatrade] from pyproject.toml."""
        values = dict(DEFAULTS)
        if PYPROJECT_FILE.exists():
            with PYPROJECT_FILE.open("rb") as file:
                tool = tomllib.load(file).get("tool", {})
            values.update(tool.get(SETTINGS_SECTION, {}))
        self._values = values

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value of a setting, or the default if there is no such key."""
        return self._values.get(key, default)

    def data_path(self, key: str) -> Path:
        """Return the path of a data file: data/users.json for users_file."""
        return Path(self.get("data_dir")) / self.get(key)

    def log_path(self, key: str) -> Path:
        """Return the path of a log file: logs/actions.log for actions_log_file."""
        return Path(self.get("logs_dir")) / self.get(key)

"""JSON storage of ValutaTrade Hub behind one DatabaseManager instance."""

import json
from typing import Any, Self

from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.infra.settings import SettingsLoader

JSON_INDENT = 2


class DatabaseManager:
    """Read and write users, portfolios and rates kept in JSON files.

    Every change goes read -> modify -> write, and a file is replaced through
    a temporary copy, so a crash in the middle never leaves half a file.
    The singleton uses __new__ for the same reason as SettingsLoader.
    """

    _instance: "DatabaseManager | None" = None

    def __new__(cls) -> Self:
        """Return the only instance of the manager."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_users(self) -> list[User]:
        """Return all registered users."""
        return [User.from_dict(record) for record in self._read("users_file", [])]

    def find_user(self, username: str) -> User | None:
        """Return the user with the name, or None."""
        for user in self.load_users():
            if user.username == username:
                return user
        return None

    def get_user(self, user_id: int) -> User | None:
        """Return the user with the identifier, or None."""
        for user in self.load_users():
            if user.user_id == user_id:
                return user
        return None

    def next_user_id(self) -> int:
        """Return the identifier for a new user: the largest one plus one."""
        return max((user.user_id for user in self.load_users()), default=0) + 1

    def add_user(self, user: User) -> None:
        """Append a user to users.json."""
        records = self._read("users_file", [])
        records.append(user.to_dict())
        self._write("users_file", records)

    def load_portfolio(self, user: User) -> Portfolio:
        """Return the portfolio of the user; without a record it is empty."""
        for record in self._read("portfolios_file", []):
            if record["user_id"] == user.user_id:
                return Portfolio.from_dict(user, record)
        return Portfolio(user)

    def save_portfolio(self, portfolio: Portfolio) -> None:
        """Replace the record of the portfolio in portfolios.json."""
        records = [
            record
            for record in self._read("portfolios_file", [])
            if record["user_id"] != portfolio.user_id
        ]
        records.append(portfolio.to_dict())
        records.sort(key=lambda record: record["user_id"])
        self._write("portfolios_file", records)

    def load_rates(self) -> dict:
        """Return the rates cache, or an empty dictionary if there is none."""
        return self._read("rates_file", {})

    def save_rates(self, cache: dict) -> None:
        """Write the rates cache."""
        self._write("rates_file", cache)

    def _read(self, key: str, default: Any) -> Any:
        """Return the data of a JSON file, or the default if there is no file."""
        path = SettingsLoader().data_path(key)
        if not path.exists():
            return default
        with path.open(encoding="utf-8") as file:
            return json.load(file)

    def _write(self, key: str, data: Any) -> None:
        """Write a JSON file through a temporary file and a rename."""
        path = SettingsLoader().data_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=JSON_INDENT)
            file.write("\n")
        temporary.replace(path)

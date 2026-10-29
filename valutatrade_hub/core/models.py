"""Domain models of ValutaTrade Hub: users, wallets and portfolios."""

import hashlib
import secrets
from datetime import datetime

MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 8


class User:
    """A registered user of the platform."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        """Create a user from stored fields.

        A new user with a plain password is created with ``User.create``.
        """
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Create a new user: check the name and password, then hash it."""
        now = datetime.now().replace(microsecond=0)
        user = cls(user_id, username, "", "", now)
        user.change_password(password)
        return user

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Restore a user from users.json"""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )

    @property
    def user_id(self) -> int:
        """return the unique user identifier."""
        return self._user_id

    @property
    def username(self) -> str:
        """Return the user name."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Set the user name: it must not be empty."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Return the password hash."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Return the salt of the password hash"""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Return the date and time of registration."""
        return self._registration_date

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """Return the SHA-256 hex digest of the password with the salt."""
        return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()

    def change_password(self, new_password: str) -> None:
        """Set a new password: check its length, renew the salt, store the hash"""
        if not isinstance(new_password, str) or len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
            )
        self._salt = secrets.token_hex(SALT_BYTES)
        self._hashed_password = self.hash_password(new_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """Return True if the password matches the stored hash."""
        candidate = self.hash_password(password, self._salt)
        return secrets.compare_digest(candidate, self._hashed_password)

    def get_user_info(self) -> str:
        """Return a description of the user without the password."""
        registered = self._registration_date.isoformat(sep=" ", timespec="seconds")
        return (
            f"Пользователь '{self._username}' (id={self._user_id}), "
            f"дата регистрации: {registered}"
        )

    def to_dict(self) -> dict:
        """Return the user as a users.json record."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(timespec="seconds"),
        }

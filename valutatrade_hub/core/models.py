"""Domain models of ValutaTrade Hub: users, wallets and portfolios."""

import hashlib
import math
import secrets
from datetime import datetime

from valutatrade_hub.core.utils import (
    AMOUNT_PRECISION,
    BASE_CURRENCY,
    EXCHANGE_RATES,
    cross_rate,
    format_amount,
    validate_amount,
    validate_currency_code,
)

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
        """Restore a user from a users.json record."""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )

    @property
    def user_id(self) -> int:
        """Return the unique user identifier."""
        return self._user_id

    @property
    def username(self) -> str:
        """Return the user name."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Set the user name; it must not be empty."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Return the password hash."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Return the salt of the password hash."""
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
        """Set a new password: check its length, renew the salt, store the hash."""
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


class Wallet:
    """A balance in one currency."""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        """Create a wallet for a currency with a starting balance."""
        self.currency_code = validate_currency_code(currency_code)
        self.balance = balance

    @property
    def balance(self) -> float:
        """Return the current balance."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        """Set the balance: a non-negative number, rounded to 8 decimals."""
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not is_number or not math.isfinite(value):
            raise ValueError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = round(float(value), AMOUNT_PRECISION)

    def deposit(self, amount: float) -> None:
        """Add a positive amount to the balance."""
        self.balance = self._balance + validate_amount(amount)

    def withdraw(self, amount: float) -> None:
        """Take a positive amount from the balance if there is enough."""
        amount = validate_amount(amount)
        if amount > self._balance:
            code = self.currency_code
            available = format_amount(code, self._balance)
            required = format_amount(code, amount)
            raise ValueError(
                f"Недостаточно средств: доступно {available} {code}, "
                f"требуется {required} {code}"
            )
        self.balance = self._balance - amount

    def get_balance_info(self) -> str:
        """Return the balance as text: BTC: 0.0500."""
        code = self.currency_code
        return f"{code}: {format_amount(code, self._balance)}"

    def to_dict(self) -> dict:
        """Return the wallet as a portfolios.json record."""
        return {"balance": self._balance}


class Portfolio:
    """All wallets of one user, keyed by currency code."""

    def __init__(self, user: User, wallets: dict[str, Wallet] | None = None) -> None:
        """Create a portfolio of the user with the given wallets."""
        self._user = user
        self._user_id = user.user_id
        self._wallets = dict(wallets) if wallets else {}

    @classmethod
    def from_dict(cls, user: User, data: dict) -> "Portfolio":
        """Restore the portfolio of the user from a portfolios.json record."""
        wallets = {
            code: Wallet(code, record["balance"])
            for code, record in data.get("wallets", {}).items()
        }
        return cls(user, wallets)

    @property
    def user(self) -> User:
        """Return the owner of the portfolio; it cannot be replaced."""
        return self._user

    @property
    def user_id(self) -> int:
        """Return the identifier of the owner."""
        return self._user_id

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Return a copy of the wallets dictionary."""
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        """Create an empty wallet for a new currency and return it."""
        code = validate_currency_code(currency_code)
        if code in self._wallets:
            raise ValueError(f"Кошелёк '{code}' уже есть в портфеле")
        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Return the wallet of the currency, or None if there is no such wallet."""
        return self._wallets.get(validate_currency_code(currency_code))

    def get_total_value(
        self,
        base_currency: str = BASE_CURRENCY,
        rates: dict[str, float] | None = None,
    ) -> float:
        """Return the value of all wallets in the base currency.

        ``rates`` maps currency codes to the price of one unit in USD;
        without it the fixed stub rates are used.
        """
        usd_rates = EXCHANGE_RATES if rates is None else rates
        base = validate_currency_code(base_currency)
        total = 0.0
        for code, wallet in self._wallets.items():
            total += wallet.balance * cross_rate(code, base, usd_rates)
        return total

    def to_dict(self) -> dict:
        """Return the portfolio as a portfolios.json record."""
        wallets = {code: wallet.to_dict() for code, wallet in self._wallets.items()}
        return {"user_id": self._user_id, "wallets": wallets}

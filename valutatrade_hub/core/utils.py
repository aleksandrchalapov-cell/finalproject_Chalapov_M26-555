"""Helpers of ValutaTrade Hub: JSON storage, input checks, rates and formats."""

import json
import math
from datetime import UTC, datetime
from pathlib import Path

DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"
JSON_INDENT = 2

BASE_CURRENCY = "USD"
RATES_TTL_SECONDS = 300
STUB_SOURCE = "Stub"
# Stub rates until the Parser Service exists: the price of one unit in USD.
EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.2361,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.00,
    "SOL": 145.12,
}
CRYPTO_CODES = frozenset({"BTC", "ETH", "SOL"})

CODE_MIN_LENGTH = 2
CODE_MAX_LENGTH = 5
AMOUNT_PRECISION = 8
FIAT_DECIMALS = 2
CRYPTO_DECIMALS = 4
RATE_DECIMALS = 2
RATE_SIGNIFICANT_DIGITS = 4
DISPLAY_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
AMOUNT_ERROR = "'amount' должен быть положительным числом"


def load_json(path: Path, default):
    """Return the data from a JSON file, or the default if there is no file."""
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data) -> None:
    """Write data to a JSON file: first to a temporary file, then rename it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=JSON_INDENT)
        file.write("\n")
    temporary.replace(path)


def validate_currency_code(code: str) -> str:
    """Return the currency code in upper case or raise ValueError."""
    normalized = code.strip().upper() if isinstance(code, str) else ""
    length_ok = CODE_MIN_LENGTH <= len(normalized) <= CODE_MAX_LENGTH
    if not (length_ok and normalized.isascii() and normalized.isalnum()):
        raise ValueError(f"Некорректный код валюты '{code}'")
    return normalized


def to_number(value: float | str) -> float | None:
    """Return the value as a float, or None if it is not a number."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_amount(value: float | str) -> float:
    """Return a positive amount rounded to 8 decimals or raise ValueError."""
    number = to_number(value)
    if number is None or not math.isfinite(number):
        raise ValueError(AMOUNT_ERROR)
    amount = round(number, AMOUNT_PRECISION)
    if amount <= 0:
        raise ValueError(AMOUNT_ERROR)
    return amount


def cross_rate(from_code: str, to_code: str, usd_rates: dict[str, float]) -> float:
    """Return the rate from one currency to another through their USD rates."""
    if from_code not in usd_rates or to_code not in usd_rates:
        raise ValueError(f"Не удалось получить курс для {from_code}→{to_code}")
    return usd_rates[from_code] / usd_rates[to_code]


def decimals_for(code: str) -> int:
    """Return how many decimals to show: 4 for crypto, 2 for fiat currencies."""
    return CRYPTO_DECIMALS if code in CRYPTO_CODES else FIAT_DECIMALS


def format_amount(code: str, amount: float) -> str:
    """Format an amount of a currency: 0.0500 for BTC, 150.00 for USD."""
    return f"{amount:.{decimals_for(code)}f}"


def format_money(code: str, amount: float) -> str:
    """Format a total with a thousands separator: 3,329.00."""
    return f"{amount:,.{decimals_for(code)}f}"


def format_rate(rate: float) -> str:
    """Format a rate with 4 significant digits, but at least 2 decimals."""
    digits_before_point = math.floor(math.log10(rate)) + 1
    decimals = max(RATE_DECIMALS, RATE_SIGNIFICANT_DIGITS - digits_before_point)
    return f"{rate:.{decimals}f}"


def utc_now() -> datetime:
    """Return the current time in UTC without microseconds."""
    return datetime.now(UTC).replace(microsecond=0)


def to_iso(moment: datetime) -> str:
    """Return a UTC time in ISO 8601 with the Z suffix: 2025-10-10T12:00:00Z."""
    return moment.astimezone(UTC).strftime(ISO_UTC_FORMAT)


def from_iso(text: str) -> datetime:
    """Parse an ISO 8601 time; a time without a zone is taken as UTC."""
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def format_timestamp(moment: datetime) -> str:
    """Format a time in the local zone for the user: 2025-10-09 00:03:22."""
    return moment.astimezone().strftime(DISPLAY_TIME_FORMAT)

"""Helpers of ValutaTrade Hub: input checks, rates, formats and a cache."""

import math
import time
from collections.abc import Callable, Hashable
from datetime import UTC, datetime
from typing import Any

from valutatrade_hub.core.currencies import get_currency

BASE_CURRENCY = "USD"
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

AMOUNT_PRECISION = 8
RATE_DECIMALS = 2
RATE_SIGNIFICANT_DIGITS = 4
DISPLAY_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
AMOUNT_ERROR = "'amount' должен быть положительным числом"


def validate_currency_code(code: str) -> str:
    """Return the code of a supported currency or raise CurrencyNotFoundError."""
    return get_currency(code).code


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
    """Return how many decimals to show: 2 for fiat, 4 for crypto currencies."""
    return get_currency(code).decimals


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


def create_cacher(ttl_seconds: float) -> Callable:
    """Remember a value for each key until its TTL or version changes."""
    cache: dict[Hashable, tuple[float, Hashable | None, Any]] = {}

    def cache_result(
        key: Hashable,
        value_func: Callable[[], Any],
        *,
        version: Hashable | None = None,
    ) -> Any:
        """Return a cached value or compute and store its current version."""
        now = time.monotonic()
        if key in cache:
            saved_at, saved_version, value = cache[key]
            if version == saved_version and now - saved_at < ttl_seconds:
                return value
        value = value_func()
        cache[key] = (now, version, value)
        return value

    cache_result.clear = cache.clear
    return cache_result

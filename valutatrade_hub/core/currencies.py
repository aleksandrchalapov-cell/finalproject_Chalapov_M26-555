"""Currencies of ValutaTrade Hub: an abstract base, fiat, crypto and a registry."""

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError

CODE_MIN_LENGTH = 2
CODE_MAX_LENGTH = 5


class Currency(ABC):
    """A currency with a human-readable name and an upper-case code."""

    decimals = 2

    def __init__(self, name: str, code: str) -> None:
        """Check the invariants: the name is not empty, the code is 2-5 capitals."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        if not _is_valid_code(code):
            raise ValueError(f"Некорректный код валюты '{code}'")
        self.name = name
        self.code = code

    @abstractmethod
    def get_display_info(self) -> str:
        """Return a one-line description of the currency for the UI and logs."""


class FiatCurrency(Currency):
    """A currency issued by a state or a monetary union."""

    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        """Create a fiat currency with the country or zone that issues it."""
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self) -> str:
        """Return: [FIAT] USD — US Dollar (Issuing: United States)."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """A cryptocurrency with its algorithm and last known market capitalization."""

    decimals = 4

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float) -> None:
        """Create a cryptocurrency with its algorithm and market capitalization."""
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    def get_display_info(self) -> str:
        """Return: [CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e12)."""
        market_cap = f"{self.market_cap:.2e}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


def _is_valid_code(code: str) -> bool:
    """Return True for 2-5 upper-case Latin letters or digits without spaces."""
    return (
        isinstance(code, str)
        and CODE_MIN_LENGTH <= len(code) <= CODE_MAX_LENGTH
        and code.isascii()
        and code.isalnum()
        and code == code.upper()
    )


_REGISTRY: dict[str, Currency] = {
    currency.code: currency
    for currency in (
        FiatCurrency("US Dollar", "USD", "United States"),
        FiatCurrency("Euro", "EUR", "Eurozone"),
        FiatCurrency("British Pound", "GBP", "United Kingdom"),
        FiatCurrency("Russian Ruble", "RUB", "Russia"),
        CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
        CryptoCurrency("Ethereum", "ETH", "Ethash", 4.47e11),
        CryptoCurrency("Solana", "SOL", "Proof of History", 6.8e10),
    )
}


def get_currency(code: str) -> Currency:
    """Return the currency by its code in any case or raise CurrencyNotFoundError."""
    key = code.strip().upper() if isinstance(code, str) else str(code)
    if key not in _REGISTRY:
        raise CurrencyNotFoundError(key)
    return _REGISTRY[key]


def supported_codes() -> list[str]:
    """Return the codes of all supported currencies in alphabetical order."""
    return sorted(_REGISTRY)


def all_currencies() -> list[Currency]:
    """Return all supported currencies: fiat first, then crypto, as registered."""
    return list(_REGISTRY.values())

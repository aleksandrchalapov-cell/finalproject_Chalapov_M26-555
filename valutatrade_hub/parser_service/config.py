"""Configuration for the exchange-rate parser."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.core.utils import BASE_CURRENCY
from valutatrade_hub.infra.settings import SettingsLoader


@dataclass
class ParserConfig:
    """Network and storage settings for the exchange-rate parser."""

    coingecko_url: str = "https://api.coingecko.com/api/v3/simple/price"
    exchangerate_url: str = "https://v6.exchangerate-api.com/v6/{key}/latest/{base}"
    base_currency: str = BASE_CURRENCY
    fiat_currencies: tuple[str, ...] = ("EUR", "GBP", "RUB")
    crypto_id_map: dict[str, str] = field(
        default_factory=lambda: {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    )
    request_timeout: float = 10.0
    exchangerate_api_key: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY"),
        repr=False,
    )
    coingecko_api_key: str | None = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY"),
        repr=False,
    )
    rates_path: Path = field(
        default_factory=lambda: SettingsLoader().data_path("rates_file"),
    )
    history_path: Path = field(
        default_factory=lambda: SettingsLoader().data_path("rates_history_file"),
    )

    @property
    def crypto_currencies(self) -> tuple[str, ...]:
        """Return the tickers configured for CoinGecko."""
        return tuple(self.crypto_id_map)

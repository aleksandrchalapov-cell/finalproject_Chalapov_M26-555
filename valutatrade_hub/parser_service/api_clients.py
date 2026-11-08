"""HTTP clients that normalize exchange rates for the parser."""

import math
from abc import ABC, abstractmethod
from http import HTTPStatus
from typing import Any

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig

EXCHANGERATE_ERRORS = {
    "invalid-key": "неверный API-ключ",
    "inactive-account": "подтвердите аккаунт",
    "quota-reached": "исчерпан лимит запросов",
    "unsupported-code": "базовая валюта не поддерживается",
    "malformed-request": "неверный формат запроса",
}


class BaseApiClient(ABC):
    """Define the common contract and handle HTTP and JSON errors."""

    source: str

    def __init__(self, config: ParserConfig) -> None:
        self._config = config

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Return validated rates keyed by pairs such as BTC_USD."""

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self._config.request_timeout,
            )
        except requests.exceptions.Timeout:
            raise ApiRequestError(
                f"{self.source}: превышено время ожидания ответа"
            ) from None
        except requests.exceptions.RequestException:
            raise ApiRequestError(f"{self.source}: сбой HTTP-запроса") from None

        status = response.status_code
        if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            raise ApiRequestError(f"{self.source}: HTTP {status}, проверьте API-ключ")
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            raise ApiRequestError(f"{self.source}: HTTP {status}, лимит запросов")
        if status != HTTPStatus.OK:
            raise ApiRequestError(f"{self.source}: HTTP {status}")

        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError:
            raise ApiRequestError(f"{self.source}: ответ не является JSON") from None
        if not isinstance(payload, dict):
            raise ApiRequestError(f"{self.source}: ожидался JSON-объект")
        return payload

    def _positive_rate(self, value: object, pair: str) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                rate = float(value)
            except OverflowError:
                rate = math.inf
            if math.isfinite(rate) and rate > 0:
                return rate
        raise ApiRequestError(f"{self.source}: нет корректного курса {pair}")


class CoinGeckoClient(BaseApiClient):
    """Fetch prices for the configured cryptocurrencies in one request."""

    source = "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        """Read each coin's price in the configured base currency."""
        base = self._config.base_currency
        quote = base.lower()
        ids = self._config.crypto_id_map
        key = self._config.coingecko_api_key
        headers = {"x-cg-demo-api-key": key} if key else None
        payload = self._get_json(
            self._config.coingecko_url,
            params={"ids": ",".join(ids.values()), "vs_currencies": quote},
            headers=headers,
        )

        rates = {}
        for code, coin_id in ids.items():
            coin = payload.get(coin_id)
            value = coin.get(quote) if isinstance(coin, dict) else None
            pair = f"{code}_{base}"
            rates[pair] = self._positive_rate(value, pair)
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Fetch fiat rates and convert them to prices in the base currency."""

    source = "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        """Invert the API's base-to-currency rates."""
        key = self._config.exchangerate_api_key
        if not key:
            raise ApiRequestError(f"{self.source}: задайте EXCHANGERATE_API_KEY")

        base = self._config.base_currency
        url = self._config.exchangerate_url.format(key=key, base=base)
        payload = self._get_json(url)
        if payload.get("result") != "success":
            error_code = payload.get("error-type")
            reason = "API отклонил запрос"
            if isinstance(error_code, str):
                reason = EXCHANGERATE_ERRORS.get(error_code, reason)
            raise ApiRequestError(f"{self.source}: {reason}")

        conversions = payload.get("conversion_rates")
        if payload.get("base_code") != base or not isinstance(conversions, dict):
            raise ApiRequestError(f"{self.source}: неверная база или формат курсов")

        rates = {}
        for code in self._config.fiat_currencies:
            direct = self._positive_rate(conversions.get(code), f"{base}_{code}")
            pair = f"{code}_{base}"
            rates[pair] = self._positive_rate(1.0 / direct, pair)
        return rates

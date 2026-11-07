"""Coordinate fetching, logging and saving exchange rates."""

import logging
from dataclasses import dataclass

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_now
from valutatrade_hub.logging_config import PARSER_LOGGER
from valutatrade_hub.parser_service.api_clients import BaseApiClient
from valutatrade_hub.parser_service.storage import RateObservation, RatesStorage

LOGGER = logging.getLogger(PARSER_LOGGER)


@dataclass(frozen=True)
class UpdateResult:
    """Report the changed pairs, the cache timestamp and any source errors."""

    updated_count: int
    last_refresh: str | None
    errors: tuple[str, ...]


class RatesUpdater:
    """Collect rates from the configured clients and save them as one batch."""

    def __init__(self, clients: list[BaseApiClient], storage: RatesStorage) -> None:
        if not clients:
            raise ValueError("Для обновления нужен хотя бы один источник курсов")
        self._clients = tuple(clients)
        self._storage = storage

    def run_update(self) -> UpdateResult:
        """Try every client and persist the observations from successful calls."""
        observations: list[RateObservation] = []
        errors: list[str] = []
        LOGGER.info("Обновление курсов началось")

        for client in self._clients:
            LOGGER.info("Запрос курсов у %s", client.source)
            try:
                rates = client.fetch_rates()
                if not rates:
                    raise ApiRequestError(
                        f"{client.source}: получен пустой набор курсов"
                    )
            except ApiRequestError as error:
                LOGGER.error("Не удалось получить курсы: %s", error.reason)
                errors.append(error.reason)
                continue

            observed_at = utc_now()
            for pair, rate in rates.items():
                observations.append(
                    RateObservation(pair, rate, observed_at, client.source)
                )
            LOGGER.info("%s вернул курсов: %d", client.source, len(rates))

        if not observations:
            LOGGER.error("Обновление завершилось без полученных курсов")
            raise ApiRequestError("; ".join(errors))

        LOGGER.info("Сохранение замеров: %d", len(observations))
        try:
            updated_count, last_refresh = self._storage.save_batch(observations)
        except (OSError, ValueError):
            LOGGER.exception("Не удалось сохранить курсы")
            raise

        LOGGER.info(
            "Обновление завершено. Обновлено пар: %d, ошибок: %d",
            updated_count,
            len(errors),
        )
        return UpdateResult(updated_count, last_refresh, tuple(errors))

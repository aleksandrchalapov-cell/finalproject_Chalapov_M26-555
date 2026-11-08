"""Run rate updates periodically from the command line."""

import argparse
import logging
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import PARSER_LOGGER, setup_logging
from valutatrade_hub.parser_service.updater import update_rates

LOGGER = logging.getLogger(PARSER_LOGGER)


def _run_scheduler(interval_seconds: int) -> None:
    """Refresh immediately, then wait between refresh attempts."""
    while True:
        try:
            update_rates()
        except (ApiRequestError, OSError, ValueError) as error:
            LOGGER.warning(
                "Повтор обновления через %d с. Причина: %s", interval_seconds, error
            )
        time.sleep(interval_seconds)


def main() -> None:
    """Read the interval, configure logs and handle Ctrl+C."""
    parser = argparse.ArgumentParser(description="Периодическое обновление курсов")
    parser.add_argument(
        "--interval",
        type=int,
        required=True,
        help="пауза между обновлениями в секундах",
    )
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval должен быть больше нуля")

    setup_logging()
    LOGGER.info("Планировщик запущен. Интервал: %d с", args.interval)
    print(f"Планировщик запущен. Интервал: {args.interval} с. Для остановки Ctrl+C.")
    try:
        _run_scheduler(args.interval)
    except KeyboardInterrupt:
        LOGGER.info("Планировщик остановлен")
        print("\nПланировщик остановлен.")


if __name__ == "__main__":
    main()

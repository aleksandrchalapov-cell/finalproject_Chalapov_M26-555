"""Domain exceptions of ValutaTrade Hub; each one builds its message for the user."""


class ValutaTradeError(Exception):
    """Base class of the errors that the command-line interface reports to the user."""


class InsufficientFundsError(ValutaTradeError):
    """A wallet does not have enough money for a withdrawal.

    The amounts come already formatted (0.0400): formatting is the job of
    core/utils.py, and importing it here would make a circular import
    (utils -> currencies -> exceptions).
    """

    def __init__(self, available: str, required: str, code: str) -> None:
        """Keep the formatted amounts and the currency code, build the message."""
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available} {code}, "
            f"требуется {required} {code}"
        )


class CurrencyNotFoundError(ValutaTradeError):
    """A currency code is not in the registry of supported currencies."""

    def __init__(self, code: str, label: str = "валюта") -> None:
        """Keep the code; label names its role, e.g. "базовая валюта"."""
        self.code = code
        super().__init__(f"Неизвестная {label} '{code}'")


class ApiRequestError(ValutaTradeError):
    """A source of exchange rates did not answer or answered with an error."""

    def __init__(self, reason: str) -> None:
        """Keep the reason and build the message."""
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")

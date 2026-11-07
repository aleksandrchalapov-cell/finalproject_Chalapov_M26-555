"""Decorators of ValutaTrade Hub: logging of domain actions and confirmation."""

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from valutatrade_hub.core.utils import format_amount, format_rate
from valutatrade_hub.logging_config import ACTIONS_LOGGER

CONFIRM_ANSWER = "y"
# Arguments that may go into the log, with their names there; never a password.
LOGGED_ARGUMENTS = {
    "username": "user",
    "user_id": "user_id",
    "currency_code": "currency",
    "amount": "amount",
}


def log_action(action: str, verbose: bool = False) -> Callable:
    """Log every call of a domain operation at INFO level.

    A successful call is described by its result (a User or a TradeResult)
    and ends with result=OK. A failed one is described by its arguments and
    ends with result=ERROR, the type and the message of the error; the error
    is raised again, the decorator never hides it. With verbose=True a trade
    also shows the wallet balance before and after.
    """

    def decorator(func: Callable) -> Callable:
        signature = inspect.signature(func)
        logger = logging.getLogger(ACTIONS_LOGGER)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            arguments = signature.bind(*args, **kwargs).arguments
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                logger.info(
                    "%s result=ERROR error_type=%s error_message=%r",
                    _describe_call(action, arguments),
                    type(error).__name__,
                    str(error),
                )
                raise
            logger.info("%s result=OK", _describe_result(action, result, verbose))
            return result

        return wrapper

    return decorator


def confirm_action(action_name: str) -> Callable:
    """Ask 'Вы уверены, что хотите выполнить "<action>"? [y/n]: ' before a call.

    Only "y" (in any case) runs the function; any other answer, Ctrl+D or
    Ctrl+C prints "Операция отменена." and returns None.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            question = f'Вы уверены, что хотите выполнить "{action_name}"? [y/n]: '
            try:
                answer = input(question)
            except (EOFError, KeyboardInterrupt):
                print()
                answer = ""
            if answer.strip().lower() != CONFIRM_ANSWER:
                print("Операция отменена.")
                return None
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _describe_call(action: str, arguments: dict[str, Any]) -> str:
    """Describe a call by its arguments: BUY user_id=1 currency='ABC' amount='1'."""
    parts = [action]
    for name, label in LOGGED_ARGUMENTS.items():
        if name in arguments:
            parts.append(f"{label}={arguments[name]!r}")
    return " ".join(parts)


def _describe_result(action: str, result: Any, verbose: bool) -> str:
    """Describe a call by its result: BUY user='alice' currency='BTC' amount=..."""
    parts = [action, f"user={result.username!r}"]
    code = getattr(result, "currency_code", None)
    if code is not None:
        parts.append(f"currency={code!r}")
        parts.append(f"amount={format_amount(code, result.amount)}")
        parts.append(f"rate={format_rate(result.rate)}")
        parts.append(f"base={result.base_currency!r}")
        if verbose:
            before = format_amount(code, result.balance_before)
            after = format_amount(code, result.balance_after)
            parts.append(f"balance={before}→{after}")
    return " ".join(parts)

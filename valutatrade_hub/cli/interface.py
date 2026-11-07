"""Interactive command-line interface of ValutaTrade Hub."""

import shlex

from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import all_currencies, supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    ValutaTradeError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import TradeResult
from valutatrade_hub.core.utils import (
    format_amount,
    format_money,
    format_rate,
    format_timestamp,
    from_iso,
    validate_amount,
    validate_currency_code,
)
from valutatrade_hub.decorators import confirm_action
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.updater import update_rates

PROMPT = "> "
OPTION_PREFIX = "--"
EXIT_COMMAND = "exit"
SEPARATOR = "-" * 33
HELP_HINT = "Введите help, чтобы увидеть команды."
WELCOME = f"ValutaTrade Hub. {HELP_HINT} Для выхода: {EXIT_COMMAND}."
RETRY_HINT = "Повторите попытку позже или проверьте подключение к сети."
COMMANDS = {
    "register": ("register --username <str> --password <str>", "зарегистрироваться"),
    "login": ("login --username <str> --password <str>", "войти в систему"),
    "show-portfolio": ("show-portfolio [--base <str>]", "показать портфель"),
    "buy": ("buy --currency <str> --amount <float>", "купить валюту"),
    "sell": ("sell --currency <str> --amount <float>", "продать валюту"),
    "get-rate": ("get-rate --from <str> --to <str>", "курс одной валюты к другой"),
    "update-rates": ("update-rates [--source <str>]", "обновить курсы"),
    "currencies": ("currencies", "список поддерживаемых валют"),
    "help": ("help [команда]", "список команд или справка по одной"),
    EXIT_COMMAND: (EXIT_COMMAND, "выйти из программы"),
}


def parse_options(
    args: list[str],
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
) -> dict[str, str]:
    """Turn ["--name", "value", ...] into {"name": "value"} and check the names."""
    allowed = set(required) | set(optional)
    options: dict[str, str] = {}
    tokens = iter(args)
    for token in tokens:
        name = token.removeprefix(OPTION_PREFIX)
        if not token.startswith(OPTION_PREFIX) or name not in allowed:
            raise ValueError(f"Неизвестный аргумент '{token}'")
        if name in options:
            raise ValueError(f"Аргумент '{token}' указан дважды")
        value = next(tokens, None)
        if value is None or value.startswith(OPTION_PREFIX):
            raise ValueError(f"Не указано значение для '{token}'")
        options[name] = value
    missing = [OPTION_PREFIX + name for name in required if name not in options]
    if missing:
        raise ValueError(f"Не указаны обязательные аргументы: {', '.join(missing)}")
    return options


class CommandLineInterface:
    """Read commands in a loop, keep the session and print the results."""

    def __init__(self) -> None:
        """Start the session without a logged-in user."""
        self._current_user: User | None = None
        self._handlers = {
            "register": self._register,
            "login": self._login,
            "show-portfolio": self._show_portfolio,
            "buy": self._buy,
            "sell": self._sell,
            "get-rate": self._get_rate,
            "update-rates": self._update_rates,
            "currencies": self._currencies,
            "help": self._help,
        }

    def run(self) -> None:
        """Read and execute commands until exit, Ctrl+D or Ctrl+C."""
        print(WELCOME)
        while True:
            try:
                line = input(PROMPT)
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not self.execute(line):
                return

    def execute(self, line: str) -> bool:
        """Execute one command line; return False when the user wants to exit."""
        try:
            tokens = shlex.split(line)
        except ValueError:
            print("Не удалось разобрать команду: проверьте кавычки")
            return True
        if not tokens:
            return True
        command, *args = tokens
        if command == EXIT_COMMAND:
            return False
        handler = self._handlers.get(command)
        if handler is None:
            print(f"Неизвестная команда '{command}'. {HELP_HINT}")
            return True
        try:
            handler(args)
        except CurrencyNotFoundError as error:
            print(error)
            print(f"Поддерживаемые валюты: {', '.join(supported_codes())}")
        except ApiRequestError as error:
            print(error)
            print(RETRY_HINT)
        except (ValutaTradeError, ValueError) as error:
            print(error)
        except OSError as error:
            print(f"Ошибка доступа к файлам: {error}")
        return True

    def _require_login(self) -> User:
        """Return the logged-in user or raise ValueError."""
        if self._current_user is None:
            raise ValueError("Сначала выполните login")
        return self._current_user

    def _register(self, args: list[str]) -> None:
        """Handle: register --username <str> --password <str>."""
        options = parse_options(args, required=("username", "password"))
        user = usecases.register(options["username"], options["password"])
        print(
            f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
            f"Войдите: login --username {user.username} --password ****"
        )

    def _login(self, args: list[str]) -> None:
        """Handle: login --username <str> --password <str>."""
        options = parse_options(args, required=("username", "password"))
        self._current_user = usecases.login(options["username"], options["password"])
        print(f"Вы вошли как '{self._current_user.username}'")

    def _show_portfolio(self, args: list[str]) -> None:
        """Handle: show-portfolio [--base <str>]."""
        user = self._require_login()
        options = parse_options(args, optional=("base",))
        summary = usecases.get_portfolio_summary(user.user_id, options.get("base"))
        if not summary.items:
            print(f"Портфель пользователя '{user.username}' пуст. Купите валюту: buy")
            return
        base = summary.base_currency
        print(f"Портфель пользователя '{user.username}' (база: {base}):")
        for wallet, value in summary.items:
            value_text = format_amount(base, value)
            print(f"- {wallet.get_balance_info()}  → {value_text} {base}")
        print(SEPARATOR)
        print(f"ИТОГО: {format_money(base, summary.total)} {base}")

    def _buy(self, args: list[str]) -> None:
        """Handle: buy --currency <str> --amount <float>."""
        user = self._require_login()
        options = parse_options(args, required=("currency", "amount"))
        result = usecases.buy(user.user_id, options["currency"], options["amount"])
        _print_trade("Покупка выполнена", result, "Оценочная стоимость покупки")

    def _sell(self, args: list[str]) -> None:
        """Handle: sell --currency <str> --amount <float>, after a confirmation."""
        user = self._require_login()
        options = parse_options(args, required=("currency", "amount"))
        code = validate_currency_code(options["currency"])
        amount = validate_amount(options["amount"])
        result = _sell_after_confirmation(user.user_id, code, amount)
        if result is not None:
            _print_trade("Продажа выполнена", result, "Оценочная выручка")

    def _get_rate(self, args: list[str]) -> None:
        """Handle: get-rate --from <str> --to <str>."""
        options = parse_options(args, required=("from", "to"))
        source = validate_currency_code(options["from"])
        target = validate_currency_code(options["to"])
        try:
            quote = usecases.get_rate(source, target)
        except ApiRequestError as error:
            print(error)
            print(f"Курс {source}→{target} недоступен. Повторите попытку позже.")
            return
        pair = f"{quote.from_code}→{quote.to_code}"
        updated = format_timestamp(quote.updated_at)
        print(f"Курс {pair}: {format_rate(quote.rate)} (обновлено: {updated})")
        reverse = f"{quote.to_code}→{quote.from_code}"
        print(f"Обратный курс {reverse}: {format_rate(1 / quote.rate)}")

    def _update_rates(self, args: list[str]) -> None:
        """Handle: update-rates [--source <str>]."""
        options = parse_options(args, optional=("source",))
        result = update_rates(options.get("source"))
        if result.errors:
            print("Обновление завершилось с ошибками.")
            for error in result.errors:
                print(f"- {error}")
        print(f"Обновлено курсов: {result.updated_count}")
        if result.last_refresh is not None:
            refreshed = format_timestamp(from_iso(result.last_refresh))
            print(f"Последнее обновление: {refreshed}")

    def _currencies(self, args: list[str]) -> None:
        """Handle: currencies; every currency describes itself."""
        parse_options(args)
        for currency in all_currencies():
            print(currency.get_display_info())

    def _help(self, args: list[str]) -> None:
        """Handle: help [command]."""
        if len(args) > 1:
            raise ValueError("Использование: help [команда]")
        if args:
            if args[0] not in COMMANDS:
                raise ValueError(f"Неизвестная команда '{args[0]}'. {HELP_HINT}")
            usage, description = COMMANDS[args[0]]
            print(f"{usage} — {description}")
            return
        table = PrettyTable(["Команда", "Описание"])
        table.align = "l"
        for usage, description in COMMANDS.values():
            table.add_row([usage, description])
        print(table)


def _print_trade(title: str, result: TradeResult, value_label: str) -> None:
    """Print the result of a purchase or a sale as in the assignment examples."""
    code = result.currency_code
    base = result.base_currency
    amount = format_amount(code, result.amount)
    rate = format_rate(result.rate)
    print(f"{title}: {amount} {code} по курсу {rate} {base}/{code}")
    print("Изменения в портфеле:")
    before = format_amount(code, result.balance_before)
    after = format_amount(code, result.balance_after)
    print(f"- {code}: было {before} → стало {after}")
    value = format_money(base, result.value_in_base)
    print(f"{value_label}: {value} {base}")


@confirm_action("продажа валюты")
def _sell_after_confirmation(user_id: int, code: str, amount: float) -> TradeResult:
    """Sell when the user answers y; otherwise the decorator returns None."""
    return usecases.sell(user_id, code, amount)


def main() -> None:
    """Configure logging and start the console interface."""
    setup_logging()
    CommandLineInterface().run()

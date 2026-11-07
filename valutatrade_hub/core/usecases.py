"""Business operations of ValutaTrade Hub, called by the command-line interface.

The singletons are used here: SettingsLoader gives the lifetime of the rates
and the default base currency, DatabaseManager reads and writes the JSON files.
"""

from dataclasses import dataclass
from datetime import datetime

from valutatrade_hub.core.exceptions import ApiRequestError, CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    BASE_CURRENCY,
    STUB_SOURCE,
    create_cacher,
    cross_rate,
    from_iso,
    utc_now,
    validate_amount,
    validate_currency_code,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import update_rates

PAIR_SEPARATOR = "_"
# Calculated quotes are cached per pair and version of their input rates.
_quote_cache = create_cacher(SettingsLoader().get("quote_cache_seconds"))


@dataclass(frozen=True)
class TradeResult:
    """The outcome of a purchase or a sale, valued in the base currency."""

    username: str
    currency_code: str
    amount: float
    base_currency: str
    rate: float
    balance_before: float
    balance_after: float
    value_in_base: float


@dataclass(frozen=True)
class PortfolioSummary:
    """The wallets of a user valued in a base currency."""

    base_currency: str
    items: tuple[tuple[Wallet, float], ...]
    total: float


@dataclass(frozen=True)
class RateQuote:
    """A rate between two currencies and the time of its update."""

    from_code: str
    to_code: str
    rate: float
    updated_at: datetime


@log_action("REGISTER")
def register(username: str, password: str) -> User:
    """Create a user with an empty portfolio; the name must be free."""
    database = DatabaseManager()
    name = username.strip()
    if database.find_user(name) is not None:
        raise ValueError(f"Имя пользователя '{name}' уже занято")
    user = User.create(database.next_user_id(), name, password)
    database.add_user(user)
    database.save_portfolio(Portfolio(user))
    return user


@log_action("LOGIN")
def login(username: str, password: str) -> User:
    """Return the user if the name exists and the password is right."""
    name = username.strip()
    user = DatabaseManager().find_user(name)
    if user is None:
        raise ValueError(f"Пользователь '{name}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


def get_portfolio_summary(
    user_id: int, base_currency: str | None = None
) -> PortfolioSummary:
    """Value every wallet of the user and the whole portfolio in the base.

    Without a base currency the default one from the settings is used.
    """
    base = _base_currency(base_currency)
    portfolio = _load_portfolio(user_id)
    wallets = portfolio.wallets
    rates = _usd_rates(_fresh_rates({base, *wallets}))
    items = tuple(
        (wallet, wallet.balance * cross_rate(code, base, rates))
        for code, wallet in wallets.items()
    )
    return PortfolioSummary(base, items, portfolio.get_total_value(base, rates))


@log_action("BUY", verbose=True)
def buy(user_id: int, currency_code: str, amount: float | str) -> TradeResult:
    """Buy an amount of a currency; a missing wallet is created first."""
    code = validate_currency_code(currency_code)
    quantity = validate_amount(amount)
    portfolio = _load_portfolio(user_id)
    wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)
    before = wallet.balance
    wallet.deposit(quantity)
    return _finish_trade(portfolio, wallet, quantity, before)


@log_action("SELL", verbose=True)
def sell(user_id: int, currency_code: str, amount: float | str) -> TradeResult:
    """Sell an amount of a currency; Wallet.withdraw checks the funds."""
    code = validate_currency_code(currency_code)
    quantity = validate_amount(amount)
    portfolio = _load_portfolio(user_id)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. "
            "Добавьте валюту: она создаётся автоматически при первой покупке."
        )
    before = wallet.balance
    wallet.withdraw(quantity)
    return _finish_trade(portfolio, wallet, quantity, before)


def get_rate(from_code: str, to_code: str) -> RateQuote:
    """Check the saved rates before reusing a calculated quote."""
    source = validate_currency_code(from_code)
    target = validate_currency_code(to_code)
    cache = _fresh_rates({source, target})
    pairs = cache.get("pairs", {})
    used_pairs = [
        pairs[_pair_key(code)] for code in (source, target) if code != BASE_CURRENCY
    ]
    version = tuple((pair["rate"], pair["updated_at"]) for pair in used_pairs)
    return _quote_cache(
        (source, target), lambda: _quote(source, target, cache), version=version
    )


def _base_currency(code: str | None) -> str:
    """Return the base currency: the given code or the default from the settings."""
    if code is None:
        code = SettingsLoader().get("default_base_currency")
    try:
        return validate_currency_code(code)
    except CurrencyNotFoundError as error:
        raise CurrencyNotFoundError(error.code, "базовая валюта") from None


def _load_portfolio(user_id: int) -> Portfolio:
    """Read the portfolio of the user with the identifier or raise ValueError."""
    database = DatabaseManager()
    user = database.get_user(user_id)
    if user is None:
        raise ValueError(f"Пользователь с id={user_id} не найден")
    return database.load_portfolio(user)


def _finish_trade(
    portfolio: Portfolio, wallet: Wallet, amount: float, before: float
) -> TradeResult:
    """Value the trade in the base currency, save the portfolio, describe it.

    The rate is taken before saving: without a rate nothing is written.
    """
    base = _base_currency(None)
    code = wallet.currency_code
    rate = cross_rate(code, base, _usd_rates(_fresh_rates({code, base})))
    DatabaseManager().save_portfolio(portfolio)
    return TradeResult(
        username=portfolio.user.username,
        currency_code=code,
        amount=amount,
        base_currency=base,
        rate=rate,
        balance_before=before,
        balance_after=wallet.balance,
        value_in_base=amount * rate,
    )


def _quote(source: str, target: str, cache: dict) -> RateQuote:
    """Build a quote from fresh rates; its time is the older of the two rates."""
    times = [
        from_iso(cache["pairs"][_pair_key(code)]["updated_at"])
        for code in (source, target)
        if code != BASE_CURRENCY
    ]
    updated_at = min(times) if times else utc_now()
    rate = cross_rate(source, target, _usd_rates(cache))
    return RateQuote(source, target, rate, updated_at)


def _pair_key(code: str) -> str:
    """Return the rates.json key of the currency against USD: BTC_USD."""
    return f"{code}{PAIR_SEPARATOR}{BASE_CURRENCY}"


def _is_stale(pair: dict) -> bool:
    """Return True if the rate is older than the lifetime from the settings."""
    age = utc_now() - from_iso(pair["updated_at"])
    return age.total_seconds() >= SettingsLoader().get("rates_ttl_seconds")


def _rates_to_refresh(cache: dict, keys: list[str]) -> list[str]:
    """List missing, simulated or expired pairs."""
    pairs = cache.get("pairs", {})
    return [
        key
        for key in keys
        if key not in pairs
        or pairs[key].get("source") == STUB_SOURCE
        or _is_stale(pairs[key])
    ]


def _fresh_rates(codes: set[str]) -> dict:
    """Return a cache with all required rates, refreshing once when needed."""
    database = DatabaseManager()
    keys = sorted(_pair_key(code) for code in codes if code != BASE_CURRENCY)
    cache = database.load_rates()
    if not _rates_to_refresh(cache, keys):
        return cache

    try:
        errors = update_rates().errors
    except ApiRequestError as error:
        errors = (error.reason,)

    cache = database.load_rates()
    unavailable = _rates_to_refresh(cache, keys)
    if unavailable:
        reason = f"нет свежих курсов для {', '.join(unavailable)}"
        if errors:
            reason += f". {'; '.join(errors)}"
        raise ApiRequestError(f"{reason}. Выполните 'update-rates'")
    return cache


def _usd_rates(cache: dict) -> dict[str, float]:
    """Return the price of one unit of each cached currency in USD."""
    rates = {BASE_CURRENCY: 1.0}
    for key, pair in cache.get("pairs", {}).items():
        code, _, quote = key.partition(PAIR_SEPARATOR)
        if quote == BASE_CURRENCY:
            rates[code] = pair["rate"]
    return rates

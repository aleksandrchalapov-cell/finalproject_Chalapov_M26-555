"""Business operations of ValutaTrade Hub, called by the command-line interface."""

from dataclasses import dataclass
from datetime import datetime

from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    BASE_CURRENCY,
    EXCHANGE_RATES,
    PORTFOLIOS_FILE,
    RATES_FILE,
    RATES_TTL_SECONDS,
    STUB_SOURCE,
    USERS_FILE,
    cross_rate,
    from_iso,
    load_json,
    save_json,
    to_iso,
    utc_now,
    validate_amount,
    validate_currency_code,
)

PAIR_SEPARATOR = "_"


@dataclass(frozen=True)
class TradeResult:
    """The outcome of a purchase or a sale."""

    currency_code: str
    amount: float
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


def register(username: str, password: str) -> User:
    """Create a user with an empty portfolio; the name must be free."""
    users = _load_users()
    name = username.strip()
    if _find_user(users, name) is not None:
        raise ValueError(f"Имя пользователя '{name}' уже занято")
    user_id = max((user.user_id for user in users), default=0) + 1
    user = User.create(user_id, name, password)
    users.append(user)
    _save_users(users)
    _save_portfolio(Portfolio(user))
    return user


def login(username: str, password: str) -> User:
    """Return the user if the name exists and the password is right."""
    name = username.strip()
    user = _find_user(_load_users(), name)
    if user is None:
        raise ValueError(f"Пользователь '{name}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


def get_portfolio_summary(
    user_id: int, base_currency: str = BASE_CURRENCY
) -> PortfolioSummary:
    """Value every wallet of the user and the whole portfolio in the base."""
    try:
        base = validate_currency_code(base_currency)
    except ValueError:
        raise ValueError(f"Неизвестная базовая валюта '{base_currency}'") from None
    portfolio = _load_portfolio(_get_user(user_id))
    wallets = portfolio.wallets
    rates = _usd_rates(_fresh_rates({base, *wallets}))
    if base not in rates:
        raise ValueError(f"Неизвестная базовая валюта '{base}'")
    items = tuple(
        (wallet, wallet.balance * cross_rate(code, base, rates))
        for code, wallet in wallets.items()
    )
    return PortfolioSummary(base, items, portfolio.get_total_value(base, rates))


def buy(user_id: int, currency_code: str, amount: float | str) -> TradeResult:
    """Buy an amount of a currency; a missing wallet is created first."""
    code = validate_currency_code(currency_code)
    quantity = validate_amount(amount)
    rate = _rate_to_base(code)
    portfolio = _load_portfolio(_get_user(user_id))
    wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)
    before = wallet.balance
    wallet.deposit(quantity)
    _save_portfolio(portfolio)
    return TradeResult(code, quantity, rate, before, wallet.balance, quantity * rate)


def sell(user_id: int, currency_code: str, amount: float | str) -> TradeResult:
    """Sell an amount of a currency from an existing wallet."""
    code = validate_currency_code(currency_code)
    quantity = validate_amount(amount)
    portfolio = _load_portfolio(_get_user(user_id))
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. "
            "Добавьте валюту: она создаётся автоматически при первой покупке."
        )
    rate = _rate_to_base(code)
    before = wallet.balance
    wallet.withdraw(quantity)
    _save_portfolio(portfolio)
    return TradeResult(code, quantity, rate, before, wallet.balance, quantity * rate)


def get_rate(from_code: str, to_code: str) -> RateQuote:
    """Return the rate between two currencies from a fresh cache."""
    source = validate_currency_code(from_code)
    target = validate_currency_code(to_code)
    cache = _fresh_rates({source, target})
    rates = _usd_rates(cache)
    if source not in rates or target not in rates:
        raise ValueError(f"Курс {source}→{target} недоступен. Повторите попытку позже.")
    times = [
        from_iso(cache["pairs"][_pair_key(code)]["updated_at"])
        for code in (source, target)
        if code != BASE_CURRENCY
    ]
    updated_at = min(times) if times else utc_now()
    return RateQuote(source, target, cross_rate(source, target, rates), updated_at)


def _load_users() -> list[User]:
    """Read all users from users.json."""
    return [User.from_dict(record) for record in load_json(USERS_FILE, [])]


def _save_users(users: list[User]) -> None:
    """Write all users to users.json."""
    save_json(USERS_FILE, [user.to_dict() for user in users])


def _find_user(users: list[User], username: str) -> User | None:
    """Return the user with the name, or None."""
    return next((user for user in users if user.username == username), None)


def _get_user(user_id: int) -> User:
    """Return the user with the identifier or raise ValueError."""
    user = next((user for user in _load_users() if user.user_id == user_id), None)
    if user is None:
        raise ValueError(f"Пользователь с id={user_id} не найден")
    return user


def _load_portfolio(user: User) -> Portfolio:
    """Read the portfolio of the user; a user without a record gets an empty one."""
    records = load_json(PORTFOLIOS_FILE, [])
    record = next((item for item in records if item["user_id"] == user.user_id), {})
    return Portfolio.from_dict(user, record)


def _save_portfolio(portfolio: Portfolio) -> None:
    """Replace the record of the portfolio in portfolios.json."""
    records = [
        item
        for item in load_json(PORTFOLIOS_FILE, [])
        if item["user_id"] != portfolio.user_id
    ]
    records.append(portfolio.to_dict())
    records.sort(key=lambda item: item["user_id"])
    save_json(PORTFOLIOS_FILE, records)


def _pair_key(code: str) -> str:
    """Return the rates.json key of the currency against USD: BTC_USD."""
    return f"{code}{PAIR_SEPARATOR}{BASE_CURRENCY}"


def _is_stale(pair: dict) -> bool:
    """Return True if the rate is older than the cache lifetime."""
    age = utc_now() - from_iso(pair["updated_at"])
    return age.total_seconds() >= RATES_TTL_SECONDS


def _fresh_rates(codes: set[str]) -> dict:
    """Return the rates cache; refresh it if a needed rate is missing or stale."""
    cache = load_json(RATES_FILE, {})
    pairs = cache.get("pairs", {})
    keys = [_pair_key(code) for code in codes if code != BASE_CURRENCY]
    if any(key not in pairs or _is_stale(pairs[key]) for key in keys):
        cache = _refresh_rates()
    return cache


def _refresh_rates() -> dict:
    """Write the stub rates to the cache; the Parser Service replaces this later."""
    now = to_iso(utc_now())
    pairs = {
        _pair_key(code): {"rate": rate, "updated_at": now, "source": STUB_SOURCE}
        for code, rate in EXCHANGE_RATES.items()
        if code != BASE_CURRENCY
    }
    cache = {"pairs": pairs, "last_refresh": now}
    save_json(RATES_FILE, cache)
    return cache


def _usd_rates(cache: dict) -> dict[str, float]:
    """Return the price of one unit of each cached currency in USD."""
    rates = {BASE_CURRENCY: 1.0}
    for key, pair in cache.get("pairs", {}).items():
        code, _, quote = key.partition(PAIR_SEPARATOR)
        if quote == BASE_CURRENCY:
            rates[code] = pair["rate"]
    return rates


def _rate_to_base(code: str) -> float:
    """Return the price of one unit of the currency in USD or raise ValueError."""
    rates = _usd_rates(_fresh_rates({code}))
    if code not in rates:
        raise ValueError(f"Не удалось получить курс для {code}→{BASE_CURRENCY}")
    return rates[code]

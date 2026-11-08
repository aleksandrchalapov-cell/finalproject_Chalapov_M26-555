# ValutaTrade Hub

ValutaTrade Hub - учебный симулятор валютного портфеля. Команды `buy`
и `sell` меняют баланс выбранной валюты и показывают оценку сделки
в базовой валюте.

Parser Service получает курсы BTC, ETH и SOL из CoinGecko, а курсы EUR,
GBP и RUB - из ExchangeRate-API. Котировки хранятся в USD за единицу валюты.
Core использует их для оценки сделок и пересчёта в выбранную базу.

## Установка и запуск

Требования - macOS или Linux, Python 3.12+, `uv` и `make`.
Для блокировки файлов курсов используется `fcntl`.

Из корня проекта:

```bash
make install
make run
```

`make install` устанавливает зависимости через `uv sync`. `make run`
запускает интерактивную команду `valutatrade`.

Для сборки и установки пакета:

```bash
make build
make package-install
valutatrade
```

Установленная команда использует текущую рабочую папку. Программа
создаёт `logs/` при запуске и `data/` при первой записи.

## Настройка источников курсов

Ключ для фиатных курсов задаётся через `EXCHANGERATE_API_KEY`. В терминале
zsh его можно ввести скрыто перед запуском приложения:

```zsh
read -rs 'EXCHANGERATE_API_KEY?Ключ ExchangeRate-API: '
printf '\n'
export EXCHANGERATE_API_KEY
```

Ключ доступен в личном кабинете [ExchangeRate-API](https://www.exchangerate-api.com/docs/standard-requests).
Для CoinGecko можно тем же способом задать `COINGECKO_API_KEY` из кабинета
[CoinGecko Demo](https://docs.coingecko.com/demo/reference/authentication).

Внутри `valutatrade` команда `update-rates` обновляет оба источника.
Для обновления одного источника используй:

```text
update-rates --source coingecko
update-rates --source exchangerate
```

Для периодического обновления запусти планировщик из корня проекта:

```bash
uv run python -m valutatrade_hub.parser_service.scheduler --interval 3600
```

Первое обновление запускается сразу. `--interval` задаёт паузу в секундах
между окончанием одной попытки и началом следующей. Остановка - `Ctrl+C`.
CLI и планировщик используют общие файлы данных при запуске из одной
рабочей папки.

## Пример сеанса

Команды ниже вводятся после приглашения `>` внутри `valutatrade`.
Строка `y` - ответ на запрос подтверждения продажи.

```text
update-rates
show-rates --top 2
show-rates --currency RUB
register --username demo --password demo1234
login --username demo --password demo1234
buy --currency BTC --amount 0.05
sell --currency BTC --amount 0.01
y
show-portfolio
get-rate --from BTC --to EUR
buy --currency ABC --amount 1
exit
```

`show-portfolio --base EUR` пересчитывает стоимость портфеля в евро.
`show-rates --currency BTC --base EUR` показывает сохранённый курс BTC к
EUR. Команда `help` выводит список команд, а `help show-rates` - справку
по выбранной команде.

## Демо

[Смотреть в браузере](https://asciinema.org/a/00E9R5Lb7UQkrBRH)
[Скачать запись](demo.cast)

Для просмотра в терминале:

```bash
asciinema play demo.cast
```

## Кэш, история и журналы

- `data/rates.json` содержит последний сохранённый курс для каждой пары,
  источник и время получения. При сбое одного поставщика парсер сохраняет
  новые курсы от второго поставщика и прежние записи первого.
- `data/exchange_rates.json` хранит историю замеров. ID состоит из пары
  и времени замера в UTC. Повторный замер с тем же ID не дублируется.
- TTL по умолчанию - 300 секунд с момента получения курса приложением.
  `get-rate`, оценка сделки и оценка портфеля при необходимости пробуют
  обновить кэш. `show-rates` читает сохранённые данные и помечает
  просроченные котировки.
- `logs/actions.log` содержит события регистрации, входа и сделок.
  `logs/parser.log` содержит результаты опроса источников и ошибки.
  Оба журнала ротируются по размеру.

TTL, базовая валюта и уровень логирования настраиваются в секции
`[tool.valutatrade]` файла `pyproject.toml` в текущей папке. Значения по
умолчанию определены в `valutatrade_hub/infra/settings.py`.

## Структура проекта

```text
data/
  users.json           Пользователи
  portfolios.json      Портфели и балансы
  rates.json           Последние курсы
  exchange_rates.json  История замеров
valutatrade_hub/
  cli/                 Разбор команд и вывод
  core/                Модели, реестр валют и бизнес-операции
  infra/               Настройки и работа с JSON
  parser_service/      API-клиенты, обновление, хранилище и планировщик
  decorators.py        Логирование действий и подтверждение продажи
  logging_config.py    Настройка журналов
main.py                Запуск из исходников
Makefile               Установка, запуск, проверка и сборка
pyproject.toml         Метаданные пакета и настройки
uv.lock                Зафиксированные зависимости
```

## Проверка кода

```bash
make lint
uv run ruff format --check .
```

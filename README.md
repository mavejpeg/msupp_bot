# Family Budget Bot

Telegram-бот для семейного бюджета Артёма и Кирилла.

Что уже включено:

- доступ только для Telegram ID `6902361169` и `5242555673`;
- PostgreSQL как основная база;
- импорт категорий, планов и текущей истории из файла `Наши доходы (6).xlsx` через `data/seed_budget.json`;
- логика планирования как в таблице: перенос обязательных платежей, частичный догон долгов, урезание бюджета при перерасходе, блокировка хотелок после минуса;
- быстрый ввод расходов сообщением: `продукты 950 магнит`;
- ввод через кнопки;
- доходы: `доход 5000 подработка` или кнопка `➕ Доход`;
- ежедневная сводка в 23:59 по Новосибирску;
- синхронизация с Google Sheets;
- экспорт Excel-отчёта из Telegram.

---

## 1. Что создать заранее

### Telegram bot token

1. Открой `@BotFather` в Telegram.
2. Напиши `/newbot`.
3. Создай бота и скопируй токен.
4. Токен вставишь в Railway в переменную `BOT_TOKEN`.

### PostgreSQL на Railway

1. Создай новый проект в Railway.
2. Нажми `New` → `Database` → `PostgreSQL`.
3. Railway сам создаст переменную `DATABASE_URL`.
4. Потом добавь сервис с этим кодом.

### Google Sheets API

Нужно для варианта `PostgreSQL + Google Sheets sync`.

1. Открой Google Cloud Console.
2. Создай проект.
3. Включи `Google Sheets API`.
4. Создай `Service Account`.
5. Создай JSON-ключ для Service Account.
6. Скопируй весь JSON в переменную Railway `GOOGLE_SERVICE_ACCOUNT_JSON`.
7. В JSON найди `client_email`.
8. Открой свою Google Таблицу → `Поделиться` → добавь этот `client_email` как редактора.
9. В `GOOGLE_SHEET_ID` вставь ID таблицы:

```text
18a-OqZWir1SxQ6WwwVU3QJGr8R_EzdTHuZOFuEDpVhE
```

---

## 2. Переменные Railway

В сервисе бота открой `Variables` и добавь:

```env
BOT_TOKEN=токен_от_BotFather
ADMIN_IDS=6902361169,5242555673
TIMEZONE=Asia/Novosibirsk
DAILY_REPORT_TIME=23:59
SEED_ON_START=true
SEED_PATH=data/seed_budget.json
GOOGLE_SHEET_ID=18a-OqZWir1SxQ6WwwVU3QJGr8R_EzdTHuZOFuEDpVhE
GOOGLE_SERVICE_ACCOUNT_JSON={...json service account...}
```

`DATABASE_URL` Railway подставит сам, если подключить PostgreSQL к сервису.

---

## 3. Как запустить на Railway

### Способ через GitHub

1. Распакуй проект.
2. Загрузи папку в GitHub-репозиторий.
3. В Railway нажми `New` → `GitHub Repo`.
4. Выбери репозиторий.
5. Railway увидит `Dockerfile` и запустит:

```bash
python -m app.bot
```

### Способ через Railway CLI

```bash
railway login
railway init
railway up
```

---

## 4. Проверка после запуска

В логах Railway должно быть:

```text
Bot started. Allowed users: [5242555673, 6902361169]
```

Потом открой своего бота в Telegram и нажми `/start`.

---

## 5. Как пользоваться

### Быстрый расход

```text
продукты 950 магнит
такси артём 430
кафе 1200 бургер
котики 1500 корм
```

Бот сам найдёт категорию по алиасам и запишет расход.

### Быстрый доход

```text
доход 5000 подработка
зп кирилл 12000
зарплата артём 30000
```

### Кнопки

- `➕ Расход` — выбор категории и ввод суммы.
- `➕ Доход` — внести доход.
- `📊 Сводка` — общий итог месяца.
- `📉 Лимиты` — план/факт/остаток по категориям.
- `🧾 План` — план расходов на месяц.
- `🔄 Sync Sheets` — вручную обновить Google Sheets.
- `📤 Excel` — скачать Excel-отчёт.

### Команды

```text
/summary
/limits
/plan
/plan 2026-07
/sync
/export
/help
```

---

## 6. Логика бюджета

Бот считает планы по принципу твоей таблицы:

### Обязательные платежи

Например коммуналка:

```text
план нового месяца = базовый план + остаток/недоплата прошлого месяца
```

### Долги

Например долг Кирилл / долг Артём:

```text
план нового месяца = базовый платёж + максимум 20% догоняния недоплаты
```

Это не даёт бюджету раздуваться до 200–240к.

### Обычные расходы

Например продукты, транспорт, такси:

```text
если был перерасход — он режет следующий месяц
если остался плюс — плюс не увеличивает следующий месяц
```

### Хотелки

Например кафе, развлечения, онлайн-шопинг, одежда, подарки:

```text
если в прошлом месяце был минус — следующий месяц бюджет 0 ₽
```

### Фиксированные категории

Например связь, котики, вредные привычки:

```text
каждый месяц обычный фиксированный план без переноса остатка
```

---

## 7. Как обновить импорт из нового Excel

Если потом снова захочешь импортировать свежий файл:

```bash
python scripts/build_seed_from_xlsx_raw.py "Наши доходы.xlsx" --out data/seed_budget.json
```

Важно: при уже заполненной базе бот не будет заново импортировать категории, чтобы не продублировать данные. Если нужен полный новый импорт, проще очистить PostgreSQL или поставить новую базу.

---

## 8. Структура проекта

```text
app/
  bot.py                 # Telegram bot
  config.py              # env variables
  db.py                  # PostgreSQL connection
  models.py              # SQLAlchemy models
  keyboards.py           # Telegram buttons
  services/
    budget.py            # расчёт планов и сводок
    sheets.py            # Google Sheets sync
    export.py            # Excel export
data/
  seed_budget.json       # импорт из твоего Excel
scripts/
  build_seed_from_xlsx_raw.py
Dockerfile
railway.toml
requirements.txt
.env.example
```

---

## 9. Важные замечания

1. Google Sheets теперь не главный источник правды. Главная база — PostgreSQL.
2. Таблица Google обновляется ботом как отчёт.
3. Если вручную менять данные в Google Sheets, бот их обратно не прочитает.
4. Добавление расходов лучше делать через Telegram, чтобы база и таблица не расходились.
5. Первый импорт уже встроен в `data/seed_budget.json`.


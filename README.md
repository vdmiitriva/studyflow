# StudyFlow

Персональный помощник для студентов: учебные задачи, предметы и дедлайны в одном месте.

## Проблема

Задачи разбросаны по чатам, тетрадям и календарю. Легко забыть дедлайн или не понять, что требует внимания сейчас. StudyFlow даёт одно API для создания, просмотра и контроля задач.

## Сейчас в проекте

Минимальный HTTP-сервер. Можно проверить, что процесс живой:

- `GET /api/v1/health` → `{"status": "ok"}`
- интерактивная документация FastAPI: `/docs`

Регистрация, предметы, задачи, JWT и Telegram **ещё не реализованы**.

## Планируемые возможности (MVP)

- регистрация и вход по email и паролю (JWT);
- предметы пользователя (CRUD);
- учебные задачи: статус `TODO` / `IN_PROGRESS` / `DONE`, дедлайн, привязка к предмету;
- список задач с фильтром и сортировкой.

Позже: уведомления и Telegram как отдельная привязка к уже существующему пользователю, не как способ регистрации.

## Стек

- Python 3.13+
- FastAPI, Uvicorn
- uv (`pyproject.toml`, `uv.lock`)

Дальше по плану: PostgreSQL, SQLAlchemy 2.x, Alembic, pytest.

## Структура

```text
studyflow/
├── src/studyflow/
│   ├── __init__.py
│   └── main.py          # приложение FastAPI, health
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
└── README.md
```

Код лежит в пакете `studyflow` (src-layout). Слои `api` / `services` / `repositories` появятся вместе с доменной логикой.

## Запуск

Нужны [uv](https://docs.astral.sh/uv/) и Python 3.13+.

```powershell
cd J:\studyflow
uv sync
uv run uvicorn studyflow.main:app --reload
```

Проверка:

- health: http://127.0.0.1:8000/api/v1/health
- Swagger: http://127.0.0.1:8000/docs

Секреты в Git не кладём. Файл `.env` в репозиторий не входит; шаблон `.env.example` появится, когда понадобятся переменные (база, JWT).

## Тесты и миграции

Пока нет. Pytest и Alembic подключим вместе с моделями и API.

## Дальше

1. PostgreSQL, SQLAlchemy, Alembic.
2. Пользователи и аутентификация.
3. Предметы и задачи.
4. Фильтрация и сортировка списка задач.
5. Архитектура уведомлений, затем Telegram.

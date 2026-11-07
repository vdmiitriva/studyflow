# StudyFlow

Персональный помощник студента: предметы, учебные задачи, сроки и расписание в одном месте.
Сейчас готова серверная часть (API). Интерфейс и Telegram Mini App в разработке.

Название «StudyFlow» рабочее.

## Что уже есть

- Регистрация, вход и выход, серверные сессии, защита от CSRF.
- Предметы: создание, чтение, изменение, удаление. У предмета свой цвет.
- Задачи: CRUD, приоритет, оценка времени, срок с часовым поясом.
- Фильтры задач по статусу, предмету и дате (`today`, `overdue`, `upcoming`), сортировка по дате создания и сроку.
- Профиль: имя и часовой пояс пользователя. Фильтры по датам учитывают этот пояс.
- Данные каждого пользователя изолированы друг от друга.
- Автоматические тесты (более 250) с покрытием около 99%.

## В разработке

Календарь и временные блоки, повторяющиеся события, свободное время, главная страница,
веб-интерфейс, Mini App в Telegram. Подробный план лежит в документе проекта.

## Технологии

Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic,
pytest, Ruff, uv, Docker.

## Запуск локально

Нужны [uv](https://docs.astral.sh/uv/) и Docker.

1. Создайте файл настроек из примера и заполните значения. `CSRF_SECRET` должен быть
   длинной случайной строкой. Для работы по обычному HTTP на своём компьютере
   можно поставить `COOKIE_SECURE=false`.

   ```powershell
   Copy-Item .env.example .env
   ```

2. Запустите PostgreSQL и установите зависимости:

   ```powershell
   docker compose up -d
   uv sync
   ```

3. Примените миграции и запустите сервер:

   ```powershell
   uv run alembic upgrade head
   uv run uvicorn studyflow.main:app --reload
   ```

Документация API откроется на <http://127.0.0.1:8000/docs>,
проверка работоспособности: `/api/v1/health`.

Файл `.env` с настоящими паролями не должен попадать в Git, он указан в `.gitignore`.

## Тесты

Тесты идут на отдельной базе `studyflow_test`. Один раз создайте её
(подставьте значение `POSTGRES_USER` из вашего `.env`) и примените миграции:

```powershell
docker compose exec db psql -U ВАШ_POSTGRES_USER -d postgres -c "CREATE DATABASE studyflow_test;"
uv run alembic -x test_db=true upgrade head
```

Проверки перед коммитом:

```powershell
uv run ruff format .
uv run ruff check .
uv run pytest -q --cov=studyflow --cov-report=term-missing
```

## Структура

```
src/studyflow/
  main.py          сборка приложения
  routers/         адреса API
  schemas/         проверка входных и выходных данных (Pydantic)
  services/        правила работы
  models/          таблицы базы (SQLAlchemy)
  dependencies/    общие проверки: вход, CSRF
migrations/        история изменений базы (Alembic)
tests/             автоматические тесты
```

## API

Все адреса начинаются с `/api/v1`.

| Группа | Адреса |
|---|---|
| Авторизация | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/csrf` |
| Профиль | `GET /auth/me`, `PATCH /auth/me` |
| Предметы | `GET/POST /subjects/`, `GET/PATCH/DELETE /subjects/{id}` |
| Задачи | `GET/POST /tasks/`, `GET/PATCH/DELETE /tasks/{id}` |
| Служебное | `GET /health` |

Запросы `POST`, `PATCH` и `DELETE` (кроме регистрации и входа) требуют заголовков
`Origin` и `X-CSRF-Token`. Токен выдаёт `GET /auth/csrf` для текущей сессии.

## Безопасность

Пароли хранятся как хеши Argon2. В базе лежит только хеш токена сессии. Cookie сессии
имеет флаги `HttpOnly` и `SameSite=Lax` (и `Secure` по умолчанию). Пользователь всегда
берётся из сессии, а не из тела запроса, и каждый запрос к данным фильтруется по нему.
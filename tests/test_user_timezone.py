from datetime import datetime, time, timedelta
from unittest.mock import Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import Task, User

ME_URL = "/api/v1/auth/me"
TASKS_URL = "/api/v1/tasks/"


def create_user(db_session) -> User:
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def test_read_current_user_returns_default_timezone(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(ME_URL)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["timezone"] == "UTC"


def test_update_timezone_saves_new_value(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(ME_URL, json={"timezone": "Europe/Moscow"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/Moscow"

    db_session.refresh(user)
    assert user.timezone == "Europe/Moscow"


@pytest.mark.parametrize(
    "bad_name",
    [
        "Mars/Olympus",
        "",
        " Europe/Moscow",
        "Europe/Moscow\n",
        "europe/moscow",
        "../etc/passwd",
    ],
)
def test_update_timezone_rejects_unknown_name(client, db_session, bad_name):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(ME_URL, json={"timezone": bad_name})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422

    db_session.refresh(user)
    assert user.timezone == "UTC"


@pytest.mark.parametrize("body", [{}, {"timezone": None}, {"timezone": 3}])
def test_update_timezone_rejects_missing_or_wrong_type(client, db_session, body):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(ME_URL, json=body)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


def test_update_timezone_requires_authentication(client):
    response = client.patch(ME_URL, json={"timezone": "Europe/Moscow"})

    assert response.status_code == 401


def noon(zone: ZoneInfo, days_ago: int) -> datetime:
    day = datetime.now(zone).date() - timedelta(days=days_ago)
    return datetime.combine(day, time(hour=12), tzinfo=zone)


def test_today_filter_uses_the_newly_saved_timezone(client, db_session):
    """After a PATCH, "today" means today in the new time zone."""
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        for zone_name in ("Pacific/Pago_Pago", "Pacific/Kiritimati"):
            zone = ZoneInfo(zone_name)
            today_task = Task(
                user_id=user.id,
                title=f"Today in {zone_name}",
                deadline=noon(zone, days_ago=0),
                status="todo",
            )
            yesterday_task = Task(
                user_id=user.id,
                title=f"Yesterday in {zone_name}",
                deadline=noon(zone, days_ago=1),
                status="todo",
            )
            db_session.add_all([today_task, yesterday_task])
            db_session.flush()

            patch_response = client.patch(ME_URL, json={"timezone": zone_name})
            assert patch_response.status_code == 200

            response = client.get(TASKS_URL, params={"date_filter": "today"})
            task_ids = {item["id"] for item in response.json()}

            assert str(today_task.id) in task_ids
            assert str(yesterday_task.id) not in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_timezone_rolls_back_on_commit_error(client, db_session, monkeypatch):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    rollback = Mock()
    test_client = TestClient(app, raise_server_exceptions=False)

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)

    try:
        response = test_client.patch(ME_URL, json={"timezone": "Europe/Moscow"})

        assert response.status_code == 500
        rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)

from uuid import uuid4

import pytest

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import User

ME_URL = "/api/v1/auth/me"


@pytest.fixture
def user(db_session):
    current_user = User(email=f"{uuid4()}@example.com")
    db_session.add(current_user)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: current_user
    yield current_user
    app.dependency_overrides.pop(get_current_user, None)


def test_register_returns_empty_name_and_default_timezone(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "correct-password"},
    )

    assert response.status_code == 201
    assert response.json()["name"] is None
    assert response.json()["timezone"] == "UTC"


def test_read_current_user_has_no_name_by_default(client, user):
    response = client.get(ME_URL)

    assert response.status_code == 200
    assert response.json()["name"] is None


def test_update_name(client, db_session, user):
    response = client.patch(ME_URL, json={"name": "Vika"})

    assert response.status_code == 200
    assert response.json()["name"] == "Vika"
    db_session.refresh(user)
    assert user.name == "Vika"


def test_update_name_strips_surrounding_spaces(client, user):
    response = client.patch(ME_URL, json={"name": "  Vika  "})

    assert response.status_code == 200
    assert response.json()["name"] == "Vika"


def test_update_name_keeps_timezone_unchanged(client, db_session, user):
    response = client.patch(ME_URL, json={"name": "Vika"})

    assert response.status_code == 200
    assert response.json()["timezone"] == "UTC"


def test_update_timezone_keeps_name_unchanged(client, db_session, user):
    user.name = "Vika"
    db_session.flush()

    response = client.patch(ME_URL, json={"timezone": "Europe/Moscow"})

    assert response.status_code == 200
    assert response.json()["name"] == "Vika"
    assert response.json()["timezone"] == "Europe/Moscow"


def test_update_name_and_timezone_together(client, db_session, user):
    response = client.patch(
        ME_URL,
        json={"name": "Vika", "timezone": "Asia/Tokyo"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Vika"
    assert response.json()["timezone"] == "Asia/Tokyo"
    db_session.refresh(user)
    assert (user.name, user.timezone) == ("Vika", "Asia/Tokyo")


@pytest.mark.parametrize("bad_name", ["", "   ", "x" * 101, None, 5])
def test_update_name_rejects_invalid_value(client, db_session, user, bad_name):
    response = client.patch(ME_URL, json={"name": bad_name})

    assert response.status_code == 422
    db_session.refresh(user)
    assert user.name is None


def test_user_without_email_can_read_and_update_profile(client, db_session):
    telegram_user = User()
    db_session.add(telegram_user)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: telegram_user

    try:
        read_response = client.get(ME_URL)
        update_response = client.patch(ME_URL, json={"name": "Vika"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert read_response.status_code == 200
    assert read_response.json()["email"] is None
    assert update_response.status_code == 200
    assert update_response.json()["email"] is None
    assert update_response.json()["name"] == "Vika"

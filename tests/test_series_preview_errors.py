from uuid import uuid4

import pytest

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import User

PREVIEW_URL = "/api/v1/blocks/series/preview"


@pytest.fixture
def login(db_session):
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


def body(**fields) -> dict:
    data = {
        "title": "English",
        "first_date": "2026-11-10",
        "last_date": "2026-11-12",
        "start_time": "09:00",
        "duration_minutes": 60,
        "repeat": "daily",
    }
    data.update(fields)
    return data


def test_preview_of_a_series_without_any_day_is_refused(client, login):
    response = client.post(
        PREVIEW_URL,
        json=body(
            first_date="2026-11-09",
            last_date="2026-11-10",
            repeat="weekly",
            weekdays=["sun"],
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "The series has no blocks in this period"


def test_preview_cannot_have_too_many_blocks(client, login, monkeypatch):
    monkeypatch.setattr("studyflow.services.series.MAX_SERIES_BLOCKS", 5)

    response = client.post(PREVIEW_URL, json=body(last_date="2026-11-15"))

    assert response.status_code == 422
    assert "more than 5" in response.json()["detail"]

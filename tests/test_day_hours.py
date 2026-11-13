from datetime import UTC, datetime, time
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import User

ME_URL = "/api/v1/auth/me"
FREE_URL = "/api/v1/calendar/free"
BLOCKS_URL = "/api/v1/blocks/"

DEFAULT_DAY = (time(8, 0), time(22, 0))


@pytest.fixture
def login(db_session):
    def log_in(**fields) -> User:
        user = User(email=f"{uuid4()}@example.com", **fields)
        db_session.add(user)
        db_session.flush()
        app.dependency_overrides[get_current_user] = lambda: user
        return user

    yield log_in
    app.dependency_overrides.pop(get_current_user, None)


def utc(hour: int, minute: int = 0, day: int = 10) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def ask(client, **params):
    query = {"from": utc(0).isoformat(), "to": utc(0, day=11).isoformat(), **params}
    return client.get(FREE_URL, params=query)


def windows_of(response) -> list[tuple[datetime, datetime]]:
    return [
        (
            datetime.fromisoformat(item["starts_at"]),
            datetime.fromisoformat(item["ends_at"]),
        )
        for item in response.json()
    ]


def saved_day(db_session, user: User) -> tuple[time, time]:
    db_session.refresh(user)
    return user.day_start, user.day_end


# ---------- profile: defaults ----------


def test_new_users_get_the_default_day(client, login):
    login()

    response = client.get(ME_URL)

    assert response.status_code == 200
    assert response.json()["day_start"] == "08:00"
    assert response.json()["day_end"] == "22:00"


# ---------- profile: changing one field or both ----------


def test_update_only_day_start(client, db_session, login):
    user = login()

    response = client.patch(ME_URL, json={"day_start": "09:00"})

    assert response.status_code == 200
    assert response.json()["day_start"] == "09:00"
    assert response.json()["day_end"] == "22:00"
    assert saved_day(db_session, user) == (time(9, 0), time(22, 0))


def test_update_only_day_end(client, db_session, login):
    user = login()

    response = client.patch(ME_URL, json={"day_end": "20:30"})

    assert response.status_code == 200
    assert response.json()["day_start"] == "08:00"
    assert response.json()["day_end"] == "20:30"
    assert saved_day(db_session, user) == (time(8, 0), time(20, 30))


def test_update_both_in_one_request(client, db_session, login):
    user = login()

    response = client.patch(ME_URL, json={"day_start": "10:00", "day_end": "18:00"})

    assert response.status_code == 200
    assert saved_day(db_session, user) == (time(10, 0), time(18, 0))


def test_both_can_move_past_the_old_values_together(client, db_session, login):
    """Neither value fits the old other one, but together they are fine."""
    user = login()

    response = client.patch(ME_URL, json={"day_start": "23:00", "day_end": "23:59"})

    assert response.status_code == 200
    assert saved_day(db_session, user) == (time(23, 0), time(23, 59))


def test_the_whole_day_is_allowed(client, db_session, login):
    login()

    response = client.patch(ME_URL, json={"day_start": "00:00", "day_end": "23:59"})

    assert response.status_code == 200
    assert response.json()["day_start"] == "00:00"
    assert response.json()["day_end"] == "23:59"


def test_updating_other_fields_keeps_the_day(client, db_session, login):
    user = login(day_start=time(9, 0), day_end=time(18, 0))

    response = client.patch(ME_URL, json={"name": "Vika"})

    assert response.status_code == 200
    assert saved_day(db_session, user) == (time(9, 0), time(18, 0))


# ---------- profile: the resulting day must be valid ----------


@pytest.mark.parametrize(
    "change",
    [
        {"day_start": "23:00"},
        {"day_start": "22:00"},
        {"day_end": "07:00"},
        {"day_end": "08:00"},
    ],
)
def test_one_field_must_fit_the_saved_value_of_the_other(
    client, db_session, login, change
):
    user = login()

    response = client.patch(ME_URL, json=change)

    assert response.status_code == 422
    assert response.json()["detail"] == "Day must end after it starts"
    assert saved_day(db_session, user) == DEFAULT_DAY


def test_the_new_saved_value_is_used_for_the_next_change(client, login):
    login()

    first = client.patch(ME_URL, json={"day_end": "18:00"})
    second = client.patch(ME_URL, json={"day_start": "17:00"})
    refused = client.patch(ME_URL, json={"day_start": "18:00"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert refused.status_code == 422


@pytest.mark.parametrize(
    ("start", "end"),
    [("18:00", "08:00"), ("10:00", "10:00")],
)
def test_two_fields_in_one_request_must_be_in_order(
    client, db_session, login, start, end
):
    user = login()

    response = client.patch(ME_URL, json={"day_start": start, "day_end": end})

    assert response.status_code == 422
    assert saved_day(db_session, user) == DEFAULT_DAY


def test_a_refused_day_does_not_change_other_fields(client, db_session, login):
    user = login()

    response = client.patch(ME_URL, json={"name": "Vika", "day_start": "23:00"})

    assert response.status_code == 422
    db_session.refresh(user)
    assert user.name is None


@pytest.mark.parametrize("field", ["day_start", "day_end"])
@pytest.mark.parametrize(
    "value",
    [
        "8:00",
        "08:00:00",
        "08:00:30",
        "24:00",
        "08:60",
        "25:00",
        "",
        "08:00+03:00",
        "08:00\n",
        "noon",
        800,
        8.5,
        True,
        None,
    ],
)
def test_day_limits_accept_only_hh_mm(client, db_session, login, field, value):
    user = login()

    response = client.patch(ME_URL, json={field: value})

    assert response.status_code == 422
    assert saved_day(db_session, user) == DEFAULT_DAY


# ---------- the database protects the rule too ----------


@pytest.mark.parametrize(
    ("start", "end"),
    [(time(22, 0), time(8, 0)), (time(9, 0), time(9, 0))],
)
def test_database_rejects_a_day_that_does_not_end_after_it_starts(
    db_session, start, end
):
    db_session.add(User(email=f"{uuid4()}@example.com", day_start=start, day_end=end))

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


# ---------- free time follows the profile ----------


def test_free_time_uses_the_profile_hours(client, login):
    login(day_start=time(9, 0), day_end=time(18, 0))

    response = ask(client)

    assert windows_of(response) == [(utc(9), utc(18))]


def test_free_time_without_settings_uses_the_default_day(client, login):
    login()

    response = ask(client)

    assert windows_of(response) == [(utc(8), utc(22))]


def test_the_request_can_override_only_the_start(client, login):
    login(day_start=time(9, 0), day_end=time(18, 0))

    response = ask(client, day_start="10:00")

    assert windows_of(response) == [(utc(10), utc(18))]


def test_the_request_can_override_only_the_end(client, login):
    login(day_start=time(9, 0), day_end=time(18, 0))

    response = ask(client, day_end="16:00")

    assert windows_of(response) == [(utc(9), utc(16))]


def test_the_request_can_override_both(client, login):
    login(day_start=time(9, 0), day_end=time(18, 0))

    response = ask(client, day_start="07:00", day_end="23:00")

    assert windows_of(response) == [(utc(7), utc(23))]


@pytest.mark.parametrize("override", [{"day_start": "19:00"}, {"day_end": "08:00"}])
def test_an_override_must_fit_the_other_profile_value(client, login, override):
    login(day_start=time(9, 0), day_end=time(18, 0))

    response = ask(client, **override)

    assert response.status_code == 422
    assert response.json()["detail"] == "Work day must end after it starts"


def test_an_override_does_not_change_the_profile(client, db_session, login):
    user = login(day_start=time(9, 0), day_end=time(18, 0))

    ask(client, day_start="12:00")

    assert saved_day(db_session, user) == (time(9, 0), time(18, 0))


@pytest.mark.parametrize("value", ["08:00:30", "08:00+03:00", "8:00", "24:00", "noon"])
def test_an_override_must_look_like_hh_mm(client, login, value):
    login()

    response = ask(client, day_start=value)

    assert response.status_code == 422


def test_changing_the_profile_changes_the_free_time(client, login):
    login()

    changed = client.patch(ME_URL, json={"day_start": "10:00"})
    response = ask(client)

    assert changed.status_code == 200
    assert windows_of(response) == [(utc(10), utc(22))]


# ---------- the preferred day never forbids a block ----------


def test_a_block_outside_the_preferred_day_can_be_created(client, login):
    login()
    body = {
        "title": "Night shift",
        "starts_at": utc(2).isoformat(),
        "ends_at": utc(4).isoformat(),
    }

    created = client.post(BLOCKS_URL, json=body)
    free = ask(client)

    assert created.status_code == 201
    assert windows_of(free) == [(utc(8), utc(22))]

from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import Subject, Task, TimeBlock, User
from studyflow.services.series import series_dates, to_instant

SERIES_URL = "/api/v1/blocks/series"
PREVIEW_URL = "/api/v1/blocks/series/preview"
BLOCKS_URL = "/api/v1/blocks/"


def utc(hour: int, minute: int = 0, day: int = 10, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


# ---------- which days and which moments (no database needed) ----------


def test_daily_series_has_a_block_every_day():
    days = series_dates(date(2026, 11, 10), date(2026, 11, 12), "daily", None)

    assert days == [date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)]


def test_weekly_series_has_only_the_chosen_days():
    days = series_dates(
        date(2026, 11, 9),
        date(2026, 11, 15),
        "weekly",
        ["mon", "wed", "fri"],
    )

    assert days == [date(2026, 11, 9), date(2026, 11, 11), date(2026, 11, 13)]


def test_the_first_and_the_last_day_are_included():
    assert series_dates(date(2026, 11, 15), date(2026, 11, 15), "daily", None) == [
        date(2026, 11, 15)
    ]
    assert series_dates(date(2026, 11, 15), date(2026, 11, 15), "weekly", ["sun"]) == [
        date(2026, 11, 15)
    ]


def test_a_repeated_weekday_counts_once():
    days = series_dates(date(2026, 11, 9), date(2026, 11, 15), "weekly", ["mon", "mon"])

    assert days == [date(2026, 11, 9)]


def test_no_matching_weekday_gives_no_days():
    days = series_dates(date(2026, 11, 9), date(2026, 11, 10), "weekly", ["sun"])

    assert days == []


@pytest.mark.parametrize(
    ("zone", "day", "hour", "expected"),
    [
        ("UTC", date(2026, 11, 10), 9, utc(9)),
        ("Asia/Tokyo", date(2026, 11, 10), 9, utc(0)),
        ("Europe/Berlin", date(2026, 10, 24), 9, utc(7, day=24, month=10)),
        ("Europe/Berlin", date(2026, 10, 25), 9, utc(8, day=25, month=10)),
        ("Europe/Berlin", date(2026, 10, 26), 9, utc(8, day=26, month=10)),
    ],
)
def test_the_same_wall_clock_time_on_every_day(zone, day, hour, expected):
    assert to_instant(day, time(hour), ZoneInfo(zone)) == expected


def test_a_time_that_does_not_exist_moves_forward():
    """On 29 March 2026 clocks in Berlin jump from 02:00 to 03:00."""
    moment = to_instant(date(2026, 3, 29), time(2, 30), ZoneInfo("Europe/Berlin"))

    assert moment == utc(1, 30, day=29, month=3)
    assert moment.astimezone(ZoneInfo("Europe/Berlin")).strftime("%H:%M") == "03:30"


def test_a_time_that_happens_twice_means_the_first_one():
    """On 25 October 2026 clocks in Berlin go back, so 02:30 happens twice."""
    moment = to_instant(date(2026, 10, 25), time(2, 30), ZoneInfo("Europe/Berlin"))

    assert moment == utc(0, 30, day=25, month=10)


# ---------- the API ----------


@pytest.fixture
def login(db_session):
    def log_in(timezone: str = "UTC") -> User:
        user = User(email=f"{uuid4()}@example.com", timezone=timezone)
        db_session.add(user)
        db_session.flush()
        app.dependency_overrides[get_current_user] = lambda: user
        return user

    yield log_in
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


def add_block(db_session, user: User, start: datetime, **fields) -> TimeBlock:
    block = TimeBlock(
        user_id=user.id,
        title=fields.pop("title", "Existing"),
        starts_at=start,
        ends_at=fields.pop("end", start + timedelta(hours=1)),
        **fields,
    )
    db_session.add(block)
    db_session.flush()
    return block


def count_blocks(db_session, user: User) -> int:
    query = select(func.count()).select_from(TimeBlock)
    return db_session.execute(query.where(TimeBlock.user_id == user.id)).scalar_one()


def starts_of(response) -> list[datetime]:
    return [
        datetime.fromisoformat(item["starts_at"]) for item in response.json()["blocks"]
    ]


# ----- preview -----


def test_preview_shows_every_block_and_saves_nothing(client, db_session, login):
    user = login()

    response = client.post(PREVIEW_URL, json=body())

    assert response.status_code == 200
    data = response.json()
    assert data["total_blocks"] == 3
    assert data["conflicting_blocks"] == 0
    assert starts_of(response) == [utc(9), utc(9, day=11), utc(9, day=12)]
    assert datetime.fromisoformat(data["blocks"][0]["ends_at"]) == utc(10)
    assert data["blocks"][0]["title"] == "English"
    assert count_blocks(db_session, user) == 0


def test_preview_of_a_weekly_series(client, login):
    login()

    response = client.post(
        PREVIEW_URL,
        json=body(
            first_date="2026-11-09",
            last_date="2026-11-15",
            repeat="weekly",
            weekdays=["mon", "wed", "fri"],
        ),
    )

    assert response.json()["total_blocks"] == 3
    assert starts_of(response) == [
        utc(9, day=9),
        utc(9, day=11),
        utc(9, day=13),
    ]


def test_preview_shows_which_blocks_overlap(client, db_session, login):
    user = login()
    existing = add_block(db_session, user, utc(9, 30, day=11), title="Lecture")

    response = client.post(PREVIEW_URL, json=body())

    data = response.json()
    assert data["conflicting_blocks"] == 1
    assert data["blocks"][0]["conflicts"] == []
    assert [c["id"] for c in data["blocks"][1]["conflicts"]] == [str(existing.id)]
    assert data["blocks"][1]["conflicts"][0]["title"] == "Lecture"
    assert count_blocks(db_session, user) == 1


def test_preview_uses_the_users_timezone(client, login):
    login("Asia/Tokyo")

    response = client.post(PREVIEW_URL, json=body())

    first = datetime.fromisoformat(response.json()["blocks"][0]["starts_at"])
    assert first == utc(0)
    assert response.json()["blocks"][0]["starts_at"].endswith("+09:00")


def test_the_same_clock_time_survives_the_end_of_summer_time(client, login):
    login("Europe/Berlin")

    response = client.post(
        PREVIEW_URL,
        json=body(first_date="2026-10-24", last_date="2026-10-26"),
    )

    assert [start.astimezone(UTC) for start in starts_of(response)] == [
        utc(7, day=24, month=10),
        utc(8, day=25, month=10),
        utc(8, day=26, month=10),
    ]


def test_a_time_that_does_not_exist_is_moved_forward(client, login):
    login("Europe/Berlin")

    response = client.post(
        PREVIEW_URL,
        json=body(first_date="2026-03-29", last_date="2026-03-29", start_time="02:30"),
    )

    data = response.json()["blocks"][0]
    assert datetime.fromisoformat(data["starts_at"]) == utc(1, 30, day=29, month=3)
    assert datetime.fromisoformat(data["ends_at"]) == utc(2, 30, day=29, month=3)


def test_a_block_lasts_exactly_its_duration_even_on_a_clock_change_day(client, login):
    login("Europe/Berlin")

    response = client.post(
        PREVIEW_URL,
        json=body(
            first_date="2026-10-25",
            last_date="2026-10-25",
            start_time="01:30",
            duration_minutes=120,
        ),
    )

    data = response.json()["blocks"][0]
    start = datetime.fromisoformat(data["starts_at"])
    end = datetime.fromisoformat(data["ends_at"])
    assert end - start == timedelta(hours=2)


# ----- creating -----


def test_create_series(client, db_session, login):
    user = login()

    response = client.post(SERIES_URL, json=body())

    assert response.status_code == 201
    blocks = response.json()
    assert len(blocks) == 3
    assert len({block["series_id"] for block in blocks}) == 1
    assert blocks[0]["series_id"] is not None
    assert {block["status"] for block in blocks} == {"planned"}
    assert {block["title"] for block in blocks} == {"English"}
    assert [datetime.fromisoformat(b["starts_at"]) for b in blocks] == [
        utc(9),
        utc(9, day=11),
        utc(9, day=12),
    ]
    assert count_blocks(db_session, user) == 3


def test_create_series_from_a_task(client, db_session, login):
    user = login()
    task = Task(user_id=user.id, title="Lab report")
    db_session.add(task)
    db_session.flush()
    data = body(task_id=str(task.id))
    del data["title"]

    response = client.post(SERIES_URL, json=data)

    assert response.status_code == 201
    assert {block["title"] for block in response.json()} == {"Lab report"}
    assert {block["task_id"] for block in response.json()} == {str(task.id)}


def test_create_series_with_a_subject(client, db_session, login):
    user = login()
    subject = Subject(name="Physics", user_id=user.id)
    db_session.add(subject)
    db_session.flush()

    response = client.post(SERIES_URL, json=body(subject_id=str(subject.id)))

    assert response.status_code == 201
    assert {block["subject_id"] for block in response.json()} == {str(subject.id)}


def test_two_series_get_different_ids(client, login):
    login()

    first = client.post(SERIES_URL, json=body(start_time="09:00"))
    second = client.post(SERIES_URL, json=body(start_time="12:00"))

    assert first.json()[0]["series_id"] != second.json()[0]["series_id"]


def test_overlapping_series_is_refused_and_nothing_is_saved(client, db_session, login):
    user = login()
    add_block(db_session, user, utc(9, 30, day=11))

    response = client.post(SERIES_URL, json=body())

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["total_conflicting_blocks"] == 1
    assert len(detail["blocks"]) == 1
    assert count_blocks(db_session, user) == 1


def test_the_conflict_warning_lists_at_most_ten_blocks(client, db_session, login):
    user = login()
    for day in range(10, 22):
        add_block(db_session, user, utc(9, 30, day=day))

    response = client.post(SERIES_URL, json=body(last_date="2026-11-21"))

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["total_conflicting_blocks"] == 12
    assert len(detail["blocks"]) == 10
    assert count_blocks(db_session, user) == 12


def test_overlapping_series_is_created_when_the_user_confirms(
    client, db_session, login
):
    user = login()
    existing = add_block(db_session, user, utc(9, 30, day=11))

    response = client.post(
        SERIES_URL,
        params={"allow_conflicts": "true"},
        json=body(),
    )

    assert response.status_code == 201
    found = [block["conflicting_block_ids"] for block in response.json()]
    assert found == [[], [str(existing.id)], []]
    assert count_blocks(db_session, user) == 4


def test_blocks_that_only_touch_are_not_a_conflict(client, db_session, login):
    user = login()
    add_block(db_session, user, utc(8, day=11))

    response = client.post(SERIES_URL, json=body())

    assert response.status_code == 201


def test_skipped_blocks_are_not_a_conflict(client, db_session, login):
    user = login()
    add_block(db_session, user, utc(9, 30, day=11), status="skipped")

    response = client.post(SERIES_URL, json=body())

    assert response.status_code == 201


def test_another_users_blocks_are_not_a_conflict(client, db_session, login):
    user = login()
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    add_block(db_session, stranger, utc(9, 30, day=11))

    response = client.post(SERIES_URL, json=body())

    assert response.status_code == 201
    assert count_blocks(db_session, user) == 3


# ----- limits -----


def test_a_series_of_183_days_is_allowed(client, login):
    login()
    first = date(2026, 11, 10)
    last = first + timedelta(days=182)

    response = client.post(
        PREVIEW_URL,
        json=body(first_date=first.isoformat(), last_date=last.isoformat()),
    )

    assert response.status_code == 200
    assert response.json()["total_blocks"] == 183


def test_a_series_of_184_days_is_refused(client, db_session, login):
    user = login()
    first = date(2026, 11, 10)
    last = first + timedelta(days=183)

    response = client.post(
        SERIES_URL,
        json=body(first_date=first.isoformat(), last_date=last.isoformat()),
    )

    assert response.status_code == 422
    assert count_blocks(db_session, user) == 0


def test_a_series_cannot_have_too_many_blocks(client, db_session, login, monkeypatch):
    user = login()
    monkeypatch.setattr("studyflow.services.series.MAX_SERIES_BLOCKS", 5)

    response = client.post(SERIES_URL, json=body(last_date="2026-11-15"))

    assert response.status_code == 422
    assert "more than 5" in response.json()["detail"]
    assert count_blocks(db_session, user) == 0


def test_a_series_without_any_day_is_refused(client, login):
    login()

    response = client.post(
        SERIES_URL,
        json=body(
            first_date="2026-11-09",
            last_date="2026-11-10",
            repeat="weekly",
            weekdays=["sun"],
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "The series has no blocks in this period"


# ----- bad requests -----


@pytest.mark.parametrize(
    "change",
    [
        {"first_date": "2026-11-13"},
        {"first_date": "2026-13-01"},
        {"first_date": "10.11.2026"},
        {"first_date": 20261110},
        {"last_date": "2026-11-09"},
        {"duration_minutes": 0},
        {"duration_minutes": 1441},
        {"duration_minutes": 1.5},
        {"start_time": "9:00"},
        {"start_time": "09:00:30"},
        {"start_time": "24:00"},
        {"start_time": 900},
        {"repeat": "monthly"},
        {"repeat": "weekly"},
        {"repeat": "weekly", "weekdays": []},
        {"repeat": "weekly", "weekdays": ["monday"]},
        {"repeat": "daily", "weekdays": ["mon"]},
        {"repeat": "daily", "weekdays": []},
        {"title": "   "},
        {"title": "x" * 201},
    ],
    ids=lambda change: str(change)[:40],
)
def test_bad_series_requests_are_refused(client, db_session, login, change):
    user = login()

    created = client.post(SERIES_URL, json=body(**change))
    previewed = client.post(PREVIEW_URL, json=body(**change))

    assert created.status_code == 422
    assert previewed.status_code == 422
    assert count_blocks(db_session, user) == 0


def test_a_series_needs_a_title_or_a_task(client, login):
    login()
    data = body()
    del data["title"]

    response = client.post(SERIES_URL, json=data)

    assert response.status_code == 422


def test_a_series_cannot_have_a_task_and_a_subject(client, db_session, login):
    user = login()
    task = Task(user_id=user.id, title="Task")
    subject = Subject(name="Physics", user_id=user.id)
    db_session.add_all([task, subject])
    db_session.flush()

    response = client.post(
        SERIES_URL,
        json=body(task_id=str(task.id), subject_id=str(subject.id)),
    )

    assert response.status_code == 422


# ----- ownership -----


@pytest.mark.parametrize("url", [SERIES_URL, PREVIEW_URL])
def test_another_users_task_is_not_found(client, db_session, login, url):
    login()
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    task = Task(user_id=stranger.id, title="Not yours")
    db_session.add(task)
    db_session.flush()

    response = client.post(url, json=body(task_id=str(task.id)))

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


@pytest.mark.parametrize("url", [SERIES_URL, PREVIEW_URL])
def test_an_unknown_task_is_not_found(client, login, url):
    login()

    response = client.post(url, json=body(task_id=str(uuid4())))

    assert response.status_code == 404


@pytest.mark.parametrize("url", [SERIES_URL, PREVIEW_URL])
def test_another_users_subject_is_not_found(client, db_session, login, url):
    login()
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    subject = Subject(name="Not yours", user_id=stranger.id)
    db_session.add(subject)
    db_session.flush()

    response = client.post(url, json=body(subject_id=str(subject.id)))

    assert response.status_code == 404
    assert response.json()["detail"] == "Subject not found"


@pytest.mark.parametrize("url", [SERIES_URL, PREVIEW_URL])
def test_series_requires_authentication(client, url):
    response = client.post(url, json=body())

    assert response.status_code == 401


# ----- one block of a series is an ordinary block -----


def test_series_blocks_are_listed_with_their_series_id(client, login):
    login()
    created = client.post(SERIES_URL, json=body())

    response = client.get(
        BLOCKS_URL,
        params={"from": utc(0).isoformat(), "to": utc(0, day=13).isoformat()},
    )

    assert response.status_code == 200
    assert {item["series_id"] for item in response.json()} == {
        created.json()[0]["series_id"]
    }


def test_editing_one_block_leaves_the_rest_of_the_series_alone(client, login):
    login()
    created = client.post(SERIES_URL, json=body()).json()
    middle = created[1]

    response = client.patch(
        f"{BLOCKS_URL}{middle['id']}",
        json={"title": "Skipped today", "status": "skipped"},
    )

    assert response.status_code == 200
    assert response.json()["series_id"] == middle["series_id"]
    others = [
        client.get(f"{BLOCKS_URL}{block['id']}").json()
        for block in (created[0], created[2])
    ]
    assert {block["title"] for block in others} == {"English"}
    assert {block["status"] for block in others} == {"planned"}


def test_deleting_one_block_leaves_the_rest_of_the_series_alone(
    client, db_session, login
):
    user = login()
    created = client.post(SERIES_URL, json=body()).json()

    response = client.delete(f"{BLOCKS_URL}{created[1]['id']}")

    assert response.status_code == 204
    assert count_blocks(db_session, user) == 2


# ----- database errors -----


def test_create_series_rolls_back_on_commit_error(
    client, db_session, login, monkeypatch
):
    login()
    rollback = Mock()

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post(SERIES_URL, json=body())

    assert response.status_code == 500
    rollback.assert_called_once()

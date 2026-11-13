from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import TimeBlock, User
from studyflow.services.calendar import merge_periods, subtract_busy, work_windows

FREE_URL = "/api/v1/calendar/free"


def utc(hour: int, minute: int = 0, day: int = 10) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


# ---------- the calculation itself (no database needed) ----------


def test_merge_of_nothing_is_nothing():
    assert merge_periods([]) == []


@pytest.mark.parametrize(
    ("periods", "expected"),
    [
        ([(utc(10), utc(12)), (utc(11), utc(13))], [(utc(10), utc(13))]),
        ([(utc(10), utc(12)), (utc(12), utc(13))], [(utc(10), utc(13))]),
        ([(utc(10), utc(15)), (utc(11), utc(12))], [(utc(10), utc(15))]),
        (
            [(utc(14), utc(15)), (utc(9), utc(10))],
            [(utc(9), utc(10)), (utc(14), utc(15))],
        ),
    ],
    ids=["overlapping", "touching", "nested", "unsorted and apart"],
)
def test_merge_periods(periods, expected):
    assert merge_periods(periods) == expected


WINDOW = (utc(8), utc(22))


@pytest.mark.parametrize(
    ("busy", "expected"),
    [
        ([], [WINDOW]),
        ([(utc(12), utc(13))], [(utc(8), utc(12)), (utc(13), utc(22))]),
        ([(utc(6), utc(9))], [(utc(9), utc(22))]),
        ([(utc(21), utc(23))], [(utc(8), utc(21))]),
        ([(utc(8), utc(10))], [(utc(10), utc(22))]),
        ([(utc(20), utc(22))], [(utc(8), utc(20))]),
        ([(utc(7), utc(23))], []),
        ([(utc(1), utc(2)), (utc(23), utc(23, 30))], [WINDOW]),
        (
            [(utc(10), utc(11)), (utc(15), utc(16))],
            [(utc(8), utc(10)), (utc(11), utc(15)), (utc(16), utc(22))],
        ),
    ],
    ids=[
        "nothing busy",
        "busy in the middle",
        "busy starts before the window",
        "busy ends after the window",
        "busy at the start",
        "busy at the end",
        "busy covers everything",
        "busy outside the window",
        "two busy periods",
    ],
)
def test_subtract_busy(busy, expected):
    assert subtract_busy(WINDOW, busy) == expected


def test_work_windows_of_one_day():
    windows = work_windows(utc(0), utc(0, day=11), ZoneInfo("UTC"), time(8), time(22))

    assert windows == [(utc(8), utc(22))]


def test_work_windows_are_cut_to_the_period():
    windows = work_windows(utc(10), utc(15), ZoneInfo("UTC"), time(8), time(22))

    assert windows == [(utc(10), utc(15))]


def test_period_outside_work_hours_has_no_windows():
    windows = work_windows(utc(23), utc(23, 30), ZoneInfo("UTC"), time(8), time(22))

    assert windows == []


def test_work_windows_of_several_days():
    windows = work_windows(utc(0), utc(0, day=13), ZoneInfo("UTC"), time(8), time(22))

    assert len(windows) == 3


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


def add_block(db_session, user: User, start: datetime, end: datetime, **fields):
    block = TimeBlock(
        user_id=user.id,
        title=fields.pop("title", "Block"),
        starts_at=start,
        ends_at=end,
        **fields,
    )
    db_session.add(block)
    db_session.flush()
    return block


def ask(client, start: datetime, end: datetime, **params):
    query = {"from": start.isoformat(), "to": end.isoformat(), **params}
    return client.get(FREE_URL, params=query)


def windows_of(response) -> list[tuple[datetime, datetime]]:
    return [
        (
            datetime.fromisoformat(item["starts_at"]),
            datetime.fromisoformat(item["ends_at"]),
        )
        for item in response.json()
    ]


def test_empty_day_is_free_during_work_hours(client, login):
    login()

    response = ask(client, utc(0), utc(0, day=11))

    assert response.status_code == 200
    assert windows_of(response) == [(utc(8), utc(22))]
    assert response.json()[0]["minutes"] == 14 * 60


def test_a_block_splits_the_free_time(client, db_session, login):
    user = login()
    add_block(db_session, user, utc(12), utc(13))

    response = ask(client, utc(0), utc(0, day=11))

    assert windows_of(response) == [(utc(8), utc(12)), (utc(13), utc(22))]


def test_free_time_is_cut_to_the_requested_period(client, login):
    login()

    response = ask(client, utc(10), utc(15))

    assert windows_of(response) == [(utc(10), utc(15))]


def test_short_gaps_are_hidden_unless_asked_for(client, db_session, login):
    user = login()
    add_block(db_session, user, utc(8), utc(10))
    add_block(db_session, user, utc(10, 20), utc(22))

    default = ask(client, utc(0), utc(0, day=11))
    short_gaps = ask(client, utc(0), utc(0, day=11), min_minutes=15)

    assert windows_of(default) == []
    assert windows_of(short_gaps) == [(utc(10), utc(10, 20))]


@pytest.mark.parametrize("status", ["skipped", "completed"])
def test_only_planned_blocks_take_up_free_time(client, db_session, login, status):
    user = login()
    add_block(db_session, user, utc(12), utc(13), status=status)

    response = ask(client, utc(0), utc(0, day=11))

    assert windows_of(response) == [(utc(8), utc(22))]


def test_other_users_blocks_do_not_take_up_free_time(client, db_session, login):
    login()
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    add_block(db_session, stranger, utc(12), utc(13))

    response = ask(client, utc(0), utc(0, day=11))

    assert windows_of(response) == [(utc(8), utc(22))]


def test_overlapping_blocks_are_counted_once(client, db_session, login):
    user = login()
    add_block(db_session, user, utc(10), utc(12))
    add_block(db_session, user, utc(11), utc(13))

    response = ask(client, utc(0), utc(0, day=11))

    assert windows_of(response) == [(utc(8), utc(10)), (utc(13), utc(22))]


def test_a_block_over_midnight_takes_up_time_on_both_days(client, db_session, login):
    user = login()
    add_block(db_session, user, utc(20), utc(9, day=11))

    response = ask(client, utc(0), utc(0, day=12))

    assert windows_of(response) == [
        (utc(8), utc(20)),
        (utc(9, day=11), utc(22, day=11)),
    ]


def test_every_day_of_the_period_gets_its_own_windows(client, login):
    login()

    response = ask(client, utc(0), utc(0, day=13))

    assert len(windows_of(response)) == 3


def test_work_day_can_be_changed(client, login):
    login()

    response = ask(client, utc(0), utc(0, day=11), day_start="09:00", day_end="18:00")

    assert windows_of(response) == [(utc(9), utc(18))]


def test_days_follow_the_users_timezone(client, login):
    login("Asia/Tokyo")
    tokyo = ZoneInfo("Asia/Tokyo")

    response = ask(
        client,
        datetime(2026, 11, 10, 0, 0, tzinfo=tokyo),
        datetime(2026, 11, 11, 0, 0, tzinfo=tokyo),
    )

    assert windows_of(response) == [(utc(23, day=9), utc(13))]
    assert response.json()[0]["starts_at"].endswith("+09:00")


def test_eight_in_the_morning_stays_eight_when_the_clocks_change(client, login):
    login("Europe/Berlin")
    berlin = ZoneInfo("Europe/Berlin")

    response = ask(
        client,
        datetime(2026, 10, 24, 0, 0, tzinfo=berlin),
        datetime(2026, 10, 27, 0, 0, tzinfo=berlin),
    )

    starts = [start.astimezone(UTC) for start, _ in windows_of(response)]
    assert starts == [
        datetime(2026, 10, 24, 6, 0, tzinfo=UTC),
        datetime(2026, 10, 25, 7, 0, tzinfo=UTC),
        datetime(2026, 10, 26, 7, 0, tzinfo=UTC),
    ]


@pytest.mark.parametrize(
    "params",
    [
        {"day_start": "18:00", "day_end": "08:00"},
        {"day_start": "08:00", "day_end": "08:00"},
        {"min_minutes": 0},
        {"min_minutes": 1441},
    ],
)
def test_bad_settings_are_rejected(client, login, params):
    login()

    response = ask(client, utc(0), utc(0, day=11), **params)

    assert response.status_code == 422


@pytest.mark.parametrize(("start", "end"), [(utc(0), utc(0)), (utc(0, day=11), utc(0))])
def test_period_must_end_after_it_starts(client, login, start, end):
    login()

    response = ask(client, start, end)

    assert response.status_code == 422


def test_period_cannot_be_longer_than_62_days(client, login):
    login()

    response = ask(client, utc(0), utc(0) + timedelta(days=63))

    assert response.status_code == 422


def test_both_ends_of_the_period_are_required(client, login):
    login()

    response = client.get(FREE_URL, params={"from": utc(0).isoformat()})

    assert response.status_code == 422


def test_period_without_timezone_is_rejected(client, login):
    login()

    response = client.get(
        FREE_URL,
        params={"from": "2026-11-10T00:00:00", "to": "2026-11-11T00:00:00+00:00"},
    )

    assert response.status_code == 422


def test_free_time_requires_authentication(client):
    response = ask(client, utc(0), utc(0, day=11))

    assert response.status_code == 401

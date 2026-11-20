from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.clock import get_now
from studyflow.main import app
from studyflow.models import Task, TimeBlock, User
from studyflow.services.home import percent_of, week_bounds

HOME_URL = "/api/v1/home"


def at(day: int, hour: int = 12, minute: int = 0, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


NOW = at(18, 10, 30)  # Wednesday 18 November 2026, 10:30 UTC
# The week of NOW: Monday 16 November 00:00 up to Monday 23 November 00:00 (UTC)


# ---------- the week and the percent (no database needed) ----------


@pytest.mark.parametrize(
    ("moment", "first_day", "next_first_day"),
    [
        (at(18, 10, 30), 16, 23),
        (at(16, 0, 0), 16, 23),
        (at(15, 23, 59), 9, 16),
        (at(22, 23, 59), 16, 23),
        (at(23, 0, 0), 23, 30),
    ],
    ids=[
        "midweek",
        "monday midnight",
        "sunday night before",
        "sunday night",
        "next monday",
    ],
)
def test_the_week_runs_from_monday_midnight_to_the_next_one(
    moment, first_day, next_first_day
):
    start, end = week_bounds(moment, ZoneInfo("UTC"))

    assert (start, end) == (at(first_day, 0), at(next_first_day, 0))


def test_the_week_starts_at_midnight_of_the_users_timezone():
    start, end = week_bounds(NOW, ZoneInfo("Asia/Tokyo"))

    assert (start, end) == (at(15, 15), at(22, 15))


def test_a_week_with_a_clock_change_still_ends_at_local_midnight():
    berlin = ZoneInfo("Europe/Berlin")
    start, end = week_bounds(datetime(2026, 10, 22, 10, tzinfo=UTC), berlin)

    assert start.astimezone(UTC) == datetime(2026, 10, 18, 22, tzinfo=UTC)
    assert end.astimezone(UTC) == datetime(2026, 10, 25, 23, tzinfo=UTC)


@pytest.mark.parametrize(
    ("completed", "total", "expected"),
    [
        (0, 0, 0),
        (0, 5, 0),
        (5, 5, 100),
        (1, 3, 33),
        (2, 3, 67),
        (1, 2, 50),
        (1, 8, 13),
        (3, 8, 38),
        (1, 6, 17),
    ],
)
def test_the_percent_is_whole_and_rounded_to_the_nearest(completed, total, expected):
    assert percent_of(completed, total) == expected


# ---------- helpers for the API tests ----------


@pytest.fixture
def login(db_session):
    def log_in(timezone: str = "UTC", **fields) -> User:
        user = User(email=f"{uuid4()}@example.com", timezone=timezone, **fields)
        db_session.add(user)
        db_session.flush()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_now] = lambda: NOW
        return user

    yield log_in
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_now, None)


def pretend_now(moment: datetime) -> None:
    app.dependency_overrides[get_now] = lambda: moment


def add_task(db_session, user: User, **fields) -> Task:
    task = Task(user_id=user.id, title="Task", **fields)
    db_session.add(task)
    db_session.flush()
    return task


def add_block(db_session, user: User, start: datetime, end=None, **fields) -> TimeBlock:
    block = TimeBlock(
        user_id=user.id,
        title="Block",
        starts_at=start,
        ends_at=end or start + timedelta(hours=1),
        **fields,
    )
    db_session.add(block)
    db_session.flush()
    return block


def make_stranger(db_session) -> User:
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    return stranger


def home(client) -> dict:
    response = client.get(HOME_URL)
    assert response.status_code == 200
    return response.json()


def week_of(client) -> dict:
    return home(client)["week"]


def free_of(client) -> list[tuple[datetime, datetime]]:
    return [
        (
            datetime.fromisoformat(item["starts_at"]),
            datetime.fromisoformat(item["ends_at"]),
        )
        for item in home(client)["free_today"]
    ]


# ---------- statistics of the week ----------


def test_an_empty_week_is_all_zeros(client, login):
    login()

    assert week_of(client) == {
        "total": 0,
        "completed": 0,
        "overdue": 0,
        "in_progress": 0,
        "todo": 0,
        "percent": 0,
    }


def test_every_task_lands_in_exactly_one_group(client, db_session, login):
    user = login()
    add_task(db_session, user, status="completed", deadline=at(17))
    add_task(db_session, user, status="todo", deadline=at(20))
    add_task(db_session, user, status="in_progress", deadline=at(21))
    add_task(db_session, user, status="todo", deadline=at(17))

    week = week_of(client)

    assert week == {
        "total": 4,
        "completed": 1,
        "overdue": 1,
        "in_progress": 1,
        "todo": 1,
        "percent": 25,
    }


def test_a_task_in_progress_with_a_passed_deadline_is_overdue(
    client, db_session, login
):
    user = login()
    add_task(db_session, user, status="in_progress", deadline=at(17))

    week = week_of(client)

    assert week["overdue"] == 1
    assert week["in_progress"] == 0


def test_a_completed_task_stays_completed_even_after_its_deadline(
    client, db_session, login
):
    user = login()
    add_task(db_session, user, status="completed", deadline=at(16))

    week = week_of(client)

    assert week["completed"] == 1
    assert week["overdue"] == 0


def test_old_unfinished_tasks_are_counted_as_debts(client, db_session, login):
    user = login()
    add_task(db_session, user, status="todo", deadline=at(2))
    add_task(db_session, user, status="in_progress", deadline=at(5))

    week = week_of(client)

    assert week["total"] == 2
    assert week["overdue"] == 2
    assert week["percent"] == 0


def test_old_finished_tasks_are_history_and_not_counted(client, db_session, login):
    user = login()
    add_task(db_session, user, status="completed", deadline=at(2))
    add_task(db_session, user, status="completed", deadline=at(15, 23, 59))

    assert week_of(client)["total"] == 0


def test_old_debts_lower_the_percent(client, db_session, login):
    user = login()
    add_task(db_session, user, status="completed", deadline=at(17))
    add_task(db_session, user, status="todo", deadline=at(2))

    assert week_of(client)["percent"] == 50


def test_the_week_starts_on_monday_at_midnight(client, db_session, login):
    user = login()
    add_task(db_session, user, status="completed", deadline=at(16, 0, 0))
    add_task(db_session, user, status="completed", deadline=at(15, 23, 59))

    assert week_of(client)["total"] == 1


def test_the_week_ends_at_next_mondays_midnight(client, db_session, login):
    user = login()
    add_task(db_session, user, status="todo", deadline=at(22, 23, 59))
    add_task(db_session, user, status="todo", deadline=at(23, 0, 0))
    add_task(db_session, user, status="completed", deadline=at(25))

    week = week_of(client)

    assert week["total"] == 1
    assert week["todo"] == 1


def test_tasks_without_a_deadline_are_not_counted(client, db_session, login):
    user = login()
    add_task(db_session, user, status="todo")
    add_task(db_session, user, status="completed")

    assert week_of(client)["total"] == 0


def test_other_users_tasks_are_not_counted(client, db_session, login):
    login()
    add_task(db_session, make_stranger(db_session), status="completed", deadline=at(17))

    assert week_of(client)["total"] == 0


@pytest.mark.parametrize(
    ("completed", "open_tasks", "percent"),
    [(1, 2, 33), (2, 1, 67), (1, 1, 50), (1, 7, 13), (3, 0, 100), (0, 2, 0)],
)
def test_the_percent_of_completed_tasks(
    client, db_session, login, completed, open_tasks, percent
):
    user = login()
    for _ in range(completed):
        add_task(db_session, user, status="completed", deadline=at(19))
    for _ in range(open_tasks):
        add_task(db_session, user, status="todo", deadline=at(20))

    week = week_of(client)

    assert week["total"] == completed + open_tasks
    assert week["percent"] == percent


def test_the_week_follows_the_users_timezone(client, db_session, login):
    user = login("Asia/Tokyo")
    # Tokyo week: 15 Nov 15:00 UTC up to 22 Nov 15:00 UTC
    add_task(db_session, user, status="completed", deadline=at(15, 16))
    add_task(db_session, user, status="todo", deadline=at(22, 14))
    add_task(db_session, user, status="completed", deadline=at(22, 16))

    week = week_of(client)

    assert week["total"] == 2
    assert week["completed"] == 1
    assert week["todo"] == 1


def test_the_same_tasks_fall_into_other_weeks_for_other_timezones(
    client, db_session, login
):
    user = login("UTC")
    add_task(db_session, user, status="completed", deadline=at(15, 16))
    add_task(db_session, user, status="completed", deadline=at(22, 16))

    assert week_of(client)["total"] == 1


def test_a_new_week_starts_on_monday(client, db_session, login):
    user = login()
    add_task(db_session, user, status="completed", deadline=at(22, 12))

    pretend_now(at(22, 23, 59))
    before = week_of(client)["total"]
    pretend_now(at(23, 0, 0))
    after = week_of(client)["total"]

    assert (before, after) == (1, 0)


# ---------- free time today ----------


def test_the_rest_of_the_day_is_free(client, login):
    login()

    data = home(client)

    assert free_of(client) == [(at(18, 10, 30), at(18, 22))]
    assert data["free_today"][0]["minutes"] == 690


def test_a_planned_block_splits_the_rest_of_the_day(client, db_session, login):
    user = login()
    add_block(db_session, user, at(18, 12), at(18, 13))

    assert free_of(client) == [
        (at(18, 10, 30), at(18, 12)),
        (at(18, 13), at(18, 22)),
    ]


def test_at_most_three_windows_are_shown_the_nearest_ones(client, db_session, login):
    user = login()
    for hour in (11, 12, 13, 14):
        add_block(db_session, user, at(18, hour), at(18, hour, 30))

    assert free_of(client) == [
        (at(18, 10, 30), at(18, 11)),
        (at(18, 11, 30), at(18, 12)),
        (at(18, 12, 30), at(18, 13)),
    ]


def test_a_block_that_is_going_on_now_pushes_the_first_window_back(
    client, db_session, login
):
    user = login()
    add_block(db_session, user, at(18, 9), at(18, 11, 30))

    assert free_of(client) == [(at(18, 11, 30), at(18, 22))]


def test_before_the_day_starts_the_first_window_starts_with_the_day(client, login):
    login()
    pretend_now(at(18, 6))

    assert free_of(client) == [(at(18, 8), at(18, 22))]


@pytest.mark.parametrize("moment", [at(18, 22, 0), at(18, 22, 30), at(18, 23, 59)])
def test_after_the_day_ends_nothing_is_offered(client, login, moment):
    login()
    pretend_now(moment)

    assert free_of(client) == []


def test_the_first_window_starts_at_the_current_moment(client, login):
    login()
    moment = NOW + timedelta(seconds=45)
    pretend_now(moment)

    assert free_of(client)[0][0] == moment


def test_a_one_minute_window_is_shown(client, db_session, login):
    user = login()
    add_block(db_session, user, at(18, 10, 31), at(18, 11))

    data = home(client)["free_today"]

    assert data[0]["minutes"] == 1
    assert datetime.fromisoformat(data[1]["starts_at"]) == at(18, 11)


def test_a_window_shorter_than_a_minute_is_not_shown(client, db_session, login):
    user = login()
    add_block(db_session, user, NOW + timedelta(seconds=30), at(18, 11))

    assert free_of(client) == [(at(18, 11), at(18, 22))]


@pytest.mark.parametrize("status", ["skipped", "completed"])
def test_only_planned_blocks_take_up_time(client, db_session, login, status):
    user = login()
    add_block(db_session, user, at(18, 12), at(18, 13), status=status)

    assert free_of(client) == [(at(18, 10, 30), at(18, 22))]


def test_other_users_blocks_take_up_no_time(client, db_session, login):
    login()
    add_block(db_session, make_stranger(db_session), at(18, 12), at(18, 13))

    assert free_of(client) == [(at(18, 10, 30), at(18, 22))]


def test_the_profile_hours_are_used(client, login):
    login(day_start=time(9, 0), day_end=time(18, 0))

    assert free_of(client) == [(at(18, 10, 30), at(18, 18))]


def test_tomorrow_is_not_offered(client, db_session, login):
    user = login()
    add_block(db_session, user, at(19, 12), at(19, 13))

    assert free_of(client) == [(at(18, 10, 30), at(18, 22))]


def test_free_time_is_shown_in_the_users_timezone(client, login):
    login("Asia/Tokyo")  # 10:30 UTC is 19:30 in Tokyo, the day ends at 22:00 there

    data = home(client)["free_today"]

    assert len(data) == 1
    assert data[0]["starts_at"].endswith("+09:00")
    assert data[0]["minutes"] == 150
    assert datetime.fromisoformat(data[0]["ends_at"]) == at(18, 13)

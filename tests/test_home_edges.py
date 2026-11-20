from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest

from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.clock import get_now
from studyflow.main import app
from studyflow.models import Task, TimeBlock, User

HOME_URL = "/api/v1/home"


def at(day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


NOW = at(18, 10, 30)  # Wednesday 18 November 2026, 10:30 UTC


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


def add_block(db_session, user: User, start: datetime, end: datetime, **fields):
    block = TimeBlock(
        user_id=user.id,
        title="Block",
        starts_at=start,
        ends_at=end,
        **fields,
    )
    db_session.add(block)
    db_session.flush()
    return block


def home(client) -> dict:
    response = client.get(HOME_URL)
    assert response.status_code == 200
    return response.json()


# ---------- the length of a free window ----------


def test_a_window_across_the_end_of_summer_time_is_measured_in_real_minutes(
    client, login
):
    login("Europe/Berlin", day_start=time(0, 0), day_end=time(23, 59))
    # 00:30 on 25 October in Berlin. At 03:00 that night the clocks go back.
    pretend_now(datetime(2026, 10, 24, 22, 30, tzinfo=UTC))

    windows = home(client)["free_today"]

    assert len(windows) == 1
    # By the wall clock it is 23 h 29 min, in reality one hour more.
    assert windows[0]["minutes"] == 24 * 60 + 29
    assert datetime.fromisoformat(windows[0]["ends_at"]) == datetime(
        2026, 10, 25, 22, 59, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("seconds", "shown", "minutes"),
    [(59, False, None), (60, True, 1), (119, True, 1), (120, True, 2)],
)
def test_a_window_needs_a_whole_minute_and_the_minutes_are_rounded_down(
    client, db_session, login, seconds, shown, minutes
):
    user = login()
    add_block(db_session, user, NOW + timedelta(seconds=seconds), at(18, 11))

    first = home(client)["free_today"][0]

    if shown:
        assert datetime.fromisoformat(first["starts_at"]) == NOW
        assert first["minutes"] == minutes
    else:
        assert datetime.fromisoformat(first["starts_at"]) == at(18, 11)


def test_a_block_covering_the_rest_of_the_day_leaves_no_windows(
    client, db_session, login
):
    user = login()
    add_block(db_session, user, at(18, 10), at(18, 22))

    assert home(client)["free_today"] == []


# ---------- the statistics of the week ----------


def test_a_task_due_exactly_now_is_not_overdue_in_the_week_statistics(
    client, db_session, login
):
    user = login()
    db_session.add(Task(user_id=user.id, title="Due now", status="todo", deadline=NOW))
    db_session.flush()

    week = home(client)["week"]

    assert (week["total"], week["todo"], week["overdue"]) == (1, 1, 0)


# ---------- stable order ----------


def test_blocks_with_the_same_start_always_come_in_the_same_order(
    client, db_session, login
):
    user = login()
    blocks = [add_block(db_session, user, at(18, 10), at(18, 11)) for _ in range(4)]

    current = home(client)["now"]

    assert [item["id"] for item in current] == [
        str(block_id) for block_id in sorted(block.id for block in blocks)
    ]
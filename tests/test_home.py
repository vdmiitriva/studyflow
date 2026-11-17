from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.clock import get_now
from studyflow.main import app
from studyflow.models import Subject, Task, TimeBlock, User

HOME_URL = "/api/v1/home"


def at(hour: int, minute: int = 0, day: int = 16) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


NOW = at(10, 30)


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


@pytest.fixture
def set_now():
    def pretend(moment: datetime) -> None:
        app.dependency_overrides[get_now] = lambda: moment

    yield pretend
    app.dependency_overrides.pop(get_now, None)


def add_block(db_session, user: User, start: datetime, end=None, **fields):
    block = TimeBlock(
        user_id=user.id,
        title=fields.pop("title", "Block"),
        starts_at=start,
        ends_at=end or start + timedelta(hours=1),
        **fields,
    )
    db_session.add(block)
    db_session.flush()
    return block


def add_subject(db_session, user: User, name="Physics", color="#112233") -> Subject:
    subject = Subject(name=name, user_id=user.id, color=color)
    db_session.add(subject)
    db_session.flush()
    return subject


def add_task(db_session, user: User, **fields) -> Task:
    task = Task(user_id=user.id, title="Lab report", **fields)
    db_session.add(task)
    db_session.flush()
    return task


def make_stranger(db_session) -> User:
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    return stranger


def ids(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


# ---------- the clock ----------


def test_the_default_clock_is_the_current_moment():
    moment = get_now()

    assert moment.tzinfo is not None
    assert abs(moment - datetime.now(UTC)) < timedelta(seconds=5)


def test_home_works_with_the_real_clock(client, db_session, login):
    user = login()
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    block = add_block(db_session, user, tomorrow)

    response = client.get(HOME_URL)

    assert response.status_code == 200
    assert response.json()["next"]["id"] == str(block.id)


# ---------- an empty home ----------


def test_a_new_user_has_an_empty_home(client, login, set_now):
    login()
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.status_code == 200
    assert response.json() == {"now": [], "next": None}


def test_home_requires_authentication(client):
    response = client.get(HOME_URL)

    assert response.status_code == 401


# ---------- the block that is going on now ----------


def test_a_block_in_progress_is_current(client, db_session, login, set_now):
    user = login()
    block = add_block(db_session, user, at(10), at(11))
    set_now(NOW)

    response = client.get(HOME_URL)

    assert ids(response.json()["now"]) == [str(block.id)]
    assert response.json()["next"] is None


@pytest.mark.parametrize(
    ("moment", "is_current"),
    [
        (at(10, 0), True),
        (at(10, 59), True),
        (at(9, 59), False),
        (at(11, 0), False),
    ],
    ids=["starts now", "one minute before the end", "one minute early", "ends now"],
)
def test_the_edges_of_the_current_block(
    client, db_session, login, set_now, moment, is_current
):
    user = login()
    block = add_block(db_session, user, at(10), at(11))
    set_now(moment)

    response = client.get(HOME_URL)

    expected = [str(block.id)] if is_current else []
    assert ids(response.json()["now"]) == expected


def test_a_block_that_starts_now_is_current_and_not_next(
    client, db_session, login, set_now
):
    user = login()
    add_block(db_session, user, at(10), at(11))
    set_now(at(10))

    response = client.get(HOME_URL)

    assert len(response.json()["now"]) == 1
    assert response.json()["next"] is None


@pytest.mark.parametrize("status", ["completed", "skipped"])
def test_only_planned_blocks_are_current(client, db_session, login, set_now, status):
    user = login()
    add_block(db_session, user, at(10), at(11), status=status)
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["now"] == []


def test_overlapping_current_blocks_are_all_listed_in_order(
    client, db_session, login, set_now
):
    user = login()
    later = add_block(db_session, user, at(10, 15), at(12), title="Later")
    earlier = add_block(db_session, user, at(10), at(11), title="Earlier")
    set_now(NOW)

    response = client.get(HOME_URL)

    assert ids(response.json()["now"]) == [str(earlier.id), str(later.id)]


def test_another_users_block_is_not_current(client, db_session, login, set_now):
    login()
    add_block(db_session, make_stranger(db_session), at(10), at(11))
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["now"] == []


# ---------- the next block ----------


def test_next_is_the_earliest_future_block(client, db_session, login, set_now):
    user = login()
    add_block(db_session, user, at(14))
    soonest = add_block(db_session, user, at(12))
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["next"]["id"] == str(soonest.id)


def test_a_current_block_does_not_hide_the_next_one(client, db_session, login, set_now):
    user = login()
    current = add_block(db_session, user, at(10), at(11))
    upcoming = add_block(db_session, user, at(12))
    set_now(NOW)

    response = client.get(HOME_URL)

    assert ids(response.json()["now"]) == [str(current.id)]
    assert response.json()["next"]["id"] == str(upcoming.id)


def test_next_ignores_past_skipped_completed_and_foreign_blocks(
    client, db_session, login, set_now
):
    user = login()
    add_block(db_session, user, at(8))
    add_block(db_session, user, at(12), status="skipped")
    add_block(db_session, user, at(12, 30), status="completed")
    add_block(db_session, make_stranger(db_session), at(13))
    wanted = add_block(db_session, user, at(15))
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["next"]["id"] == str(wanted.id)


def test_a_block_that_starts_later_the_same_minute_is_next(
    client, db_session, login, set_now
):
    user = login()
    block = add_block(db_session, user, NOW + timedelta(seconds=1))
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["next"]["id"] == str(block.id)


# ---------- the subject and its color ----------


def test_a_block_has_the_subject_it_was_given(client, db_session, login, set_now):
    user = login()
    subject = add_subject(db_session, user, name="Physics", color="#E11D48")
    add_block(db_session, user, at(10), at(11), subject_id=subject.id)
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["now"][0]["subject"] == {
        "id": str(subject.id),
        "name": "Physics",
        "color": "#E11D48",
    }


def test_a_block_gets_the_subject_of_its_task(client, db_session, login, set_now):
    user = login()
    subject = add_subject(db_session, user, name="History", color="#00AA55")
    task = add_task(db_session, user, subject_id=subject.id)
    add_block(db_session, user, at(10), at(11), task_id=task.id)
    set_now(NOW)

    response = client.get(HOME_URL)

    block = response.json()["now"][0]
    assert block["task_id"] == str(task.id)
    assert block["subject"]["color"] == "#00AA55"
    assert block["subject"]["name"] == "History"


def test_a_block_whose_task_has_no_subject_has_no_subject(
    client, db_session, login, set_now
):
    user = login()
    task = add_task(db_session, user)
    add_block(db_session, user, at(10), at(11), task_id=task.id)
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["now"][0]["subject"] is None


def test_a_standalone_block_has_no_subject(client, db_session, login, set_now):
    user = login()
    add_block(db_session, user, at(10), at(11))
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["now"][0]["subject"] is None
    assert response.json()["now"][0]["task_id"] is None


def test_the_next_block_also_has_its_subject(client, db_session, login, set_now):
    user = login()
    subject = add_subject(db_session, user, color="#4F46E5")
    add_block(db_session, user, at(12), subject_id=subject.id)
    set_now(NOW)

    response = client.get(HOME_URL)

    assert response.json()["next"]["subject"]["color"] == "#4F46E5"


# ---------- time zone ----------


def test_times_are_shown_in_the_users_timezone(client, db_session, login, set_now):
    user = login("Asia/Tokyo")
    add_block(db_session, user, at(10), at(11))
    set_now(NOW)

    response = client.get(HOME_URL)

    block = response.json()["now"][0]
    assert block["starts_at"].endswith("+09:00")
    assert datetime.fromisoformat(block["starts_at"]) == at(10)
    assert datetime.fromisoformat(block["ends_at"]) == at(11)

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.clock import get_now
from studyflow.main import app
from studyflow.models import Subject, Task, User
from studyflow.services.home import reason_of, urgency_of

HOME_URL = "/api/v1/home"


def at(hour: int = 0, minute: int = 0, day: int = 16) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


NOW = at(10, 30)  # Monday 16 November 2026, 10:30 UTC


# ---------- urgency and reasons (no database needed) ----------


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [
        (None, None),
        (at(10, 29), "overdue"),
        (at(0, 0, day=1), "overdue"),
        (NOW, "today"),
        (at(23, 59), "today"),
        (at(0, 0, day=17), "soon"),
        (at(23, 0, day=19), "soon"),
        (at(0, 0, day=20), "later"),
    ],
    ids=[
        "no deadline",
        "a minute ago",
        "long ago",
        "exactly now",
        "end of today",
        "tomorrow",
        "in three days",
        "in four days",
    ],
)
def test_urgency_by_the_exact_moment_and_the_date(deadline, expected):
    assert urgency_of(deadline, NOW, ZoneInfo("UTC")) == expected


def test_the_date_is_the_users_date_not_utc():
    tokyo = ZoneInfo("Asia/Tokyo")

    # 23:00 UTC on the 16th is already the 17th in Tokyo, where it is 19:30 now.
    assert urgency_of(at(23), NOW, tokyo) == "soon"
    assert urgency_of(at(23), NOW, ZoneInfo("UTC")) == "today"


@pytest.mark.parametrize(
    ("priority", "deadline", "urgency", "expected"),
    [
        ("low", at(1), "overdue", "overdue"),
        ("high", at(1), "overdue", "overdue"),
        ("medium", NOW, "today", "due_today"),
        ("high", NOW, "today", "due_today"),
        ("medium", at(0, 0, day=18), "soon", "due_soon"),
        ("high", at(0, 0, day=30), "later", "high_priority"),
        ("high", None, None, "high_priority"),
        ("medium", None, None, "no_deadline"),
        ("low", None, None, "no_deadline"),
        ("medium", at(0, 0, day=30), "later", None),
        ("low", at(0, 0, day=30), "later", None),
    ],
)
def test_the_reason_for_a_suggestion(priority, deadline, urgency, expected):
    assert reason_of(priority, deadline, urgency) == expected


# ---------- helpers for the API tests ----------


@pytest.fixture
def login(db_session):
    def log_in(timezone: str = "UTC") -> User:
        user = User(email=f"{uuid4()}@example.com", timezone=timezone)
        db_session.add(user)
        db_session.flush()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_now] = lambda: NOW
        return user

    yield log_in
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_now, None)


def add_task(db_session, user: User, title: str = "Task", **fields) -> Task:
    task = Task(user_id=user.id, title=title, **fields)
    db_session.add(task)
    db_session.flush()
    return task


def add_subject(db_session, user: User, color: str = "#112233") -> Subject:
    subject = Subject(name="Physics", user_id=user.id, color=color)
    db_session.add(subject)
    db_session.flush()
    return subject


def make_stranger(db_session) -> User:
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    return stranger


def home(client) -> dict:
    response = client.get(HOME_URL)
    assert response.status_code == 200
    return response.json()


def ids_of(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


def created(day: int) -> datetime:
    return datetime(2026, 11, day, 8, 0, tzinfo=UTC)


# ---------- the current task ----------


def test_without_tasks_there_is_no_current_task_and_nothing_else(client, login):
    login()

    data = home(client)

    assert data["current_task"] is None
    assert data["suggested"] == []
    assert data["deadlines"] == {"overdue_total": 0, "upcoming_total": 0, "tasks": []}


def test_the_task_in_progress_is_current(client, db_session, login):
    user = login()
    task = add_task(db_session, user, status="in_progress", priority="high")
    add_task(db_session, user, status="todo")
    add_task(db_session, user, status="completed")

    current = home(client)["current_task"]

    assert current["id"] == str(task.id)
    assert current["status"] == "in_progress"
    assert current["priority"] == "high"


def test_among_several_the_nearest_deadline_is_current(client, db_session, login):
    user = login()
    add_task(db_session, user, status="in_progress", deadline=at(12, day=20))
    nearest = add_task(db_session, user, status="in_progress", deadline=at(12, day=18))
    add_task(db_session, user, status="in_progress")

    assert home(client)["current_task"]["id"] == str(nearest.id)


def test_an_overdue_task_in_progress_can_be_current(client, db_session, login):
    user = login()
    overdue = add_task(db_session, user, status="in_progress", deadline=at(8))
    add_task(db_session, user, status="in_progress", deadline=at(12, day=20))

    assert home(client)["current_task"]["id"] == str(overdue.id)


def test_a_task_without_a_deadline_is_current_only_if_nothing_else_is(
    client, db_session, login
):
    user = login()
    lone = add_task(db_session, user, status="in_progress")

    assert home(client)["current_task"]["id"] == str(lone.id)

    dated = add_task(db_session, user, status="in_progress", deadline=at(12, day=25))

    assert home(client)["current_task"]["id"] == str(dated.id)


def test_with_equal_deadlines_the_earlier_created_task_is_current(
    client, db_session, login
):
    user = login()
    deadline = at(12, day=20)
    add_task(
        db_session,
        user,
        "Later",
        status="in_progress",
        deadline=deadline,
        created_at=created(12),
    )
    first = add_task(
        db_session,
        user,
        "First",
        status="in_progress",
        deadline=deadline,
        created_at=created(10),
    )

    assert home(client)["current_task"]["id"] == str(first.id)


def test_another_users_task_is_never_current(client, db_session, login):
    login()
    add_task(db_session, make_stranger(db_session), status="in_progress")

    assert home(client)["current_task"] is None


def test_the_current_task_carries_its_subject_deadline_and_urgency(
    client, db_session, login
):
    user = login()
    subject = add_subject(db_session, user, color="#E11D48")
    add_task(
        db_session,
        user,
        status="in_progress",
        subject_id=subject.id,
        deadline=at(18),
        estimate_minutes=90,
    )

    current = home(client)["current_task"]

    assert current["subject"] == {
        "id": str(subject.id),
        "name": "Physics",
        "color": "#E11D48",
    }
    assert datetime.fromisoformat(current["deadline"]) == at(18)
    assert current["urgency"] == "today"
    assert current["estimate_minutes"] == 90


def test_a_task_without_subject_or_deadline_has_neither(client, db_session, login):
    user = login()
    add_task(db_session, user, status="in_progress")

    current = home(client)["current_task"]

    assert current["subject"] is None
    assert current["deadline"] is None
    assert current["urgency"] is None


def test_deadlines_are_shown_in_the_users_timezone(client, db_session, login):
    user = login("Asia/Tokyo")
    add_task(db_session, user, status="in_progress", deadline=at(18))

    current = home(client)["current_task"]

    assert current["deadline"].endswith("+09:00")
    assert datetime.fromisoformat(current["deadline"]) == at(18)


# ---------- suggested tasks ----------


def test_at_most_three_unfinished_tasks_are_suggested(client, db_session, login):
    user = login()
    for number in range(5):
        add_task(db_session, user, f"Task {number}", deadline=at(12, day=20 + number))
    add_task(db_session, user, "Done", status="completed", deadline=at(12, day=17))

    suggested = home(client)["suggested"]

    assert [item["title"] for item in suggested] == ["Task 0", "Task 1", "Task 2"]


def test_only_the_current_task_is_left_out(client, db_session, login):
    user = login()
    current = add_task(
        db_session,
        user,
        "Current",
        status="in_progress",
        deadline=at(12, day=17),
    )
    other = add_task(
        db_session,
        user,
        "Other in progress",
        status="in_progress",
        deadline=at(12, day=18),
    )
    todo = add_task(db_session, user, "Todo", deadline=at(12, day=19))

    data = home(client)

    assert data["current_task"]["id"] == str(current.id)
    assert ids_of(data["suggested"]) == [str(other.id), str(todo.id)]


def test_the_nearest_deadline_comes_first_then_priority_then_estimate(
    client, db_session, login
):
    user = login()
    add_task(
        db_session,
        user,
        "A",
        deadline=at(12, day=20),
        priority="low",
        estimate_minutes=30,
    )
    long_ = add_task(
        db_session,
        user,
        "B",
        deadline=at(12, day=20),
        priority="high",
        estimate_minutes=120,
    )
    short = add_task(
        db_session,
        user,
        "C",
        deadline=at(12, day=20),
        priority="high",
        estimate_minutes=60,
    )
    early = add_task(db_session, user, "D", deadline=at(12, day=18), priority="low")

    suggested = home(client)["suggested"]

    assert ids_of(suggested) == [str(early.id), str(short.id), str(long_.id)]


def test_medium_priority_comes_between_high_and_low(client, db_session, login):
    user = login()
    deadline = at(12, day=20)
    low = add_task(db_session, user, "Low", deadline=deadline, priority="low")
    high = add_task(db_session, user, "High", deadline=deadline, priority="high")
    medium = add_task(db_session, user, "Medium", deadline=deadline, priority="medium")

    suggested = home(client)["suggested"]

    assert ids_of(suggested) == [str(high.id), str(medium.id), str(low.id)]


def test_a_task_without_an_estimate_comes_after_one_with_an_estimate(
    client, db_session, login
):
    user = login()
    deadline = at(12, day=20)
    without = add_task(db_session, user, "Without", deadline=deadline)
    with_estimate = add_task(
        db_session,
        user,
        "With",
        deadline=deadline,
        estimate_minutes=90,
    )

    suggested = home(client)["suggested"]

    assert ids_of(suggested) == [str(with_estimate.id), str(without.id)]


def test_with_everything_equal_the_earlier_created_task_comes_first(
    client, db_session, login
):
    user = login()
    deadline = at(12, day=20)
    later = add_task(
        db_session,
        user,
        "Later",
        deadline=deadline,
        created_at=created(12),
    )
    first = add_task(
        db_session,
        user,
        "First",
        deadline=deadline,
        created_at=created(10),
    )

    assert ids_of(home(client)["suggested"]) == [str(first.id), str(later.id)]


def test_tasks_without_a_deadline_come_last(client, db_session, login):
    user = login()
    none_high = add_task(db_session, user, "No deadline, high", priority="high")
    none_low = add_task(db_session, user, "No deadline, low", priority="low")
    dated = add_task(db_session, user, "Dated", deadline=at(12, day=29), priority="low")

    suggested = home(client)["suggested"]

    assert ids_of(suggested) == [str(dated.id), str(none_high.id), str(none_low.id)]


def test_overdue_tasks_are_suggested_first(client, db_session, login):
    user = login()
    add_task(db_session, user, "Soon", deadline=at(12, day=17))
    old = add_task(db_session, user, "Old", deadline=at(9, day=2))

    assert home(client)["suggested"][0]["id"] == str(old.id)


def test_other_users_tasks_are_not_suggested(client, db_session, login):
    login()
    add_task(db_session, make_stranger(db_session), deadline=at(12, day=17))

    assert home(client)["suggested"] == []


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"deadline": at(9)}, "overdue"),
        ({"deadline": at(18)}, "due_today"),
        ({"deadline": at(12, day=18)}, "due_soon"),
        ({"deadline": at(12, day=30), "priority": "high"}, "high_priority"),
        ({"priority": "high"}, "high_priority"),
        ({}, "no_deadline"),
        ({"deadline": at(12, day=30)}, None),
    ],
    ids=[
        "overdue",
        "due today",
        "due soon",
        "far deadline but high priority",
        "no deadline but high priority",
        "no deadline",
        "far deadline, nothing special",
    ],
)
def test_every_suggestion_says_why(client, db_session, login, fields, reason):
    user = login()
    add_task(db_session, user, **fields)

    suggested = home(client)["suggested"]

    assert suggested[0]["reason"] == reason


def test_a_suggestion_carries_its_subject_and_urgency(client, db_session, login):
    user = login()
    subject = add_subject(db_session, user, color="#00AA55")
    add_task(db_session, user, subject_id=subject.id, deadline=at(12, day=18))

    item = home(client)["suggested"][0]

    assert item["subject"]["color"] == "#00AA55"
    assert item["urgency"] == "soon"


# ---------- deadlines ----------


def test_deadlines_list_overdue_first_oldest_first_then_the_future(
    client, db_session, login
):
    user = login()
    far = add_task(db_session, user, "Far", deadline=at(12, day=25))
    old = add_task(db_session, user, "Old", deadline=at(9, day=2))
    near = add_task(db_session, user, "Near", deadline=at(18))
    recent = add_task(db_session, user, "Recent", deadline=at(9, day=15))

    tasks = home(client)["deadlines"]["tasks"]

    assert ids_of(tasks) == [str(old.id), str(recent.id), str(near.id), str(far.id)]


def test_deadlines_show_at_most_five_tasks(client, db_session, login):
    user = login()
    for number in range(8):
        add_task(db_session, user, f"Task {number}", deadline=at(12, day=17 + number))

    deadlines = home(client)["deadlines"]

    assert len(deadlines["tasks"]) == 5


def test_the_totals_count_every_task_not_only_the_listed_ones(
    client, db_session, login
):
    user = login()
    for number in range(7):
        add_task(db_session, user, f"Overdue {number}", deadline=at(9, day=1 + number))
    for number in range(4):
        add_task(
            db_session,
            user,
            f"Upcoming {number}",
            deadline=at(12, day=17 + number),
        )

    deadlines = home(client)["deadlines"]

    assert deadlines["overdue_total"] == 7
    assert deadlines["upcoming_total"] == 4
    assert len(deadlines["tasks"]) == 5
    assert {item["urgency"] for item in deadlines["tasks"]} == {"overdue"}


def test_completed_tasks_and_tasks_without_a_deadline_are_not_counted(
    client, db_session, login
):
    user = login()
    add_task(db_session, user, status="completed", deadline=at(9, day=2))
    add_task(db_session, user, status="completed", deadline=at(12, day=20))
    add_task(db_session, user)
    kept = add_task(db_session, user, status="in_progress", deadline=at(12, day=20))

    deadlines = home(client)["deadlines"]

    assert ids_of(deadlines["tasks"]) == [str(kept.id)]
    assert deadlines["overdue_total"] == 0
    assert deadlines["upcoming_total"] == 1


def test_a_deadline_exactly_now_has_not_passed_yet(client, db_session, login):
    user = login()
    add_task(db_session, user, deadline=NOW)

    deadlines = home(client)["deadlines"]

    assert deadlines["overdue_total"] == 0
    assert deadlines["upcoming_total"] == 1
    assert deadlines["tasks"][0]["urgency"] == "today"


def test_a_task_in_progress_with_a_passed_deadline_is_overdue(
    client, db_session, login
):
    user = login()
    add_task(db_session, user, status="in_progress", deadline=at(9))

    data = home(client)

    assert data["deadlines"]["overdue_total"] == 1
    assert data["deadlines"]["tasks"][0]["urgency"] == "overdue"
    assert data["current_task"]["urgency"] == "overdue"


def test_the_current_task_is_also_in_the_deadlines(client, db_session, login):
    user = login()
    task = add_task(db_session, user, status="in_progress", deadline=at(18))

    data = home(client)

    assert data["current_task"]["id"] == str(task.id)
    assert ids_of(data["deadlines"]["tasks"]) == [str(task.id)]


def test_other_users_deadlines_are_not_shown_or_counted(client, db_session, login):
    login()
    stranger = make_stranger(db_session)
    add_task(db_session, stranger, deadline=at(9, day=2))
    add_task(db_session, stranger, deadline=at(12, day=20))

    deadlines = home(client)["deadlines"]

    assert deadlines == {"overdue_total": 0, "upcoming_total": 0, "tasks": []}


def test_deadline_urgency_follows_the_users_timezone(client, db_session, login):
    user = login("Asia/Tokyo")
    add_task(db_session, user, deadline=at(23))

    item = home(client)["deadlines"]["tasks"][0]

    assert item["urgency"] == "soon"


def test_the_deadline_subject_color_is_included(client, db_session, login):
    user = login()
    subject = add_subject(db_session, user, color="#4F46E5")
    add_task(db_session, user, subject_id=subject.id, deadline=at(18))

    item = home(client)["deadlines"]["tasks"][0]

    assert item["subject"]["color"] == "#4F46E5"

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import Subject, Task, User
from studyflow.models.subject import DEFAULT_SUBJECT_COLOR

SUBJECTS_URL = "/api/v1/subjects/"
TASKS_URL = "/api/v1/tasks/"

BAD_COLORS = [
    "red",
    "#FFF",
    "#GGGGGG",
    "4F46E5",
    "#4F46E5\n",
    "",
    " #4F46E5",
    "#12345678",
]


def create_user(db_session) -> User:
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def user(db_session):
    """A logged-in user: the real login is replaced by this user."""
    current_user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: current_user
    yield current_user
    app.dependency_overrides.pop(get_current_user, None)


def add_subject(db_session, user: User, **fields) -> Subject:
    subject = Subject(name="Math", user_id=user.id, **fields)
    db_session.add(subject)
    db_session.flush()
    return subject


def add_task(db_session, user: User, **fields) -> Task:
    task = Task(user_id=user.id, title="My task", **fields)
    db_session.add(task)
    db_session.flush()
    return task


# ---------- subject color: API ----------


def test_create_subject_without_color_uses_default(client, user):
    response = client.post(SUBJECTS_URL, json={"name": "Math"})

    assert response.status_code == 201
    assert response.json()["color"] == DEFAULT_SUBJECT_COLOR


def test_create_subject_with_chosen_color(client, user):
    response = client.post(SUBJECTS_URL, json={"name": "Math", "color": "#e11d48"})

    assert response.status_code == 201
    assert response.json()["color"] == "#e11d48"


@pytest.mark.parametrize("bad_color", BAD_COLORS)
def test_create_subject_rejects_invalid_color(client, user, bad_color):
    response = client.post(SUBJECTS_URL, json={"name": "Math", "color": bad_color})

    assert response.status_code == 422


def test_get_subject_returns_its_color(client, db_session, user):
    subject = add_subject(db_session, user, color="#112233")

    response = client.get(f"{SUBJECTS_URL}{subject.id}")

    assert response.status_code == 200
    assert response.json()["color"] == "#112233"


def test_update_subject_color(client, db_session, user):
    subject = add_subject(db_session, user)

    response = client.patch(f"{SUBJECTS_URL}{subject.id}", json={"color": "#00AA55"})

    assert response.status_code == 200
    assert response.json()["color"] == "#00AA55"
    db_session.refresh(subject)
    assert subject.color == "#00AA55"


@pytest.mark.parametrize("bad_color", BAD_COLORS)
def test_update_subject_rejects_invalid_color(client, db_session, user, bad_color):
    subject = add_subject(db_session, user)

    response = client.patch(f"{SUBJECTS_URL}{subject.id}", json={"color": bad_color})

    assert response.status_code == 422
    db_session.refresh(subject)
    assert subject.color == DEFAULT_SUBJECT_COLOR


def test_update_subject_with_null_color_returns_422(client, db_session, user):
    subject = add_subject(db_session, user)

    response = client.patch(f"{SUBJECTS_URL}{subject.id}", json={"color": None})

    assert response.status_code == 422
    assert response.json()["detail"] == "Color cannot be null"


def test_update_subject_with_null_name_returns_422(client, db_session, user):
    subject = add_subject(db_session, user)

    response = client.patch(f"{SUBJECTS_URL}{subject.id}", json={"name": None})

    assert response.status_code == 422
    assert response.json()["detail"] == "Name cannot be null"


# ---------- task priority and estimate: API ----------


def test_create_task_has_default_priority_and_no_estimate(client, user):
    response = client.post(TASKS_URL, json={"title": "Prepare project"})

    assert response.status_code == 201
    assert response.json()["priority"] == "medium"
    assert response.json()["estimate_minutes"] is None


def test_create_task_with_priority_and_estimate(client, user):
    response = client.post(
        TASKS_URL,
        json={"title": "Prepare project", "priority": "high", "estimate_minutes": 90},
    )

    assert response.status_code == 201
    assert response.json()["priority"] == "high"
    assert response.json()["estimate_minutes"] == 90


@pytest.mark.parametrize("minutes", [1, 1440])
def test_create_task_accepts_estimate_limits(client, user, minutes):
    response = client.post(
        TASKS_URL,
        json={"title": "Prepare project", "estimate_minutes": minutes},
    )

    assert response.status_code == 201
    assert response.json()["estimate_minutes"] == minutes


@pytest.mark.parametrize("priority", ["urgent", "", "HIGH", None])
def test_create_task_rejects_invalid_priority(client, user, priority):
    response = client.post(
        TASKS_URL,
        json={"title": "Prepare project", "priority": priority},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("minutes", [0, -5, 1441, 1.5, "ninety"])
def test_create_task_rejects_invalid_estimate(client, user, minutes):
    response = client.post(
        TASKS_URL,
        json={"title": "Prepare project", "estimate_minutes": minutes},
    )

    assert response.status_code == 422


def test_update_task_priority(client, db_session, user):
    task = add_task(db_session, user)

    response = client.patch(f"{TASKS_URL}{task.id}", json={"priority": "low"})

    assert response.status_code == 200
    assert response.json()["priority"] == "low"


def test_update_task_rejects_invalid_priority(client, db_session, user):
    task = add_task(db_session, user)

    response = client.patch(f"{TASKS_URL}{task.id}", json={"priority": "urgent"})

    assert response.status_code == 422


def test_update_task_with_null_priority_returns_422(client, db_session, user):
    task = add_task(db_session, user)

    response = client.patch(f"{TASKS_URL}{task.id}", json={"priority": None})

    assert response.status_code == 422
    assert response.json()["detail"] == "Priority cannot be null"


def test_update_task_can_set_and_clear_estimate(client, db_session, user):
    task = add_task(db_session, user)

    set_response = client.patch(f"{TASKS_URL}{task.id}", json={"estimate_minutes": 45})
    clear_response = client.patch(
        f"{TASKS_URL}{task.id}",
        json={"estimate_minutes": None},
    )

    assert set_response.status_code == 200
    assert set_response.json()["estimate_minutes"] == 45
    assert clear_response.status_code == 200
    assert clear_response.json()["estimate_minutes"] is None


def test_update_task_rejects_invalid_estimate(client, db_session, user):
    task = add_task(db_session, user)

    response = client.patch(f"{TASKS_URL}{task.id}", json={"estimate_minutes": 0})

    assert response.status_code == 422


# ---------- the database protects itself even if the API is bypassed ----------


def test_database_rejects_invalid_subject_color(db_session):
    owner = create_user(db_session)
    db_session.add(Subject(name="Math", user_id=owner.id, color="blue"))

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_database_rejects_invalid_task_priority(db_session):
    owner = create_user(db_session)
    db_session.add(Task(user_id=owner.id, title="Task", priority="urgent"))

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


@pytest.mark.parametrize("minutes", [0, -1, 1441])
def test_database_rejects_estimate_out_of_range(db_session, minutes):
    owner = create_user(db_session)
    db_session.add(Task(user_id=owner.id, title="Task", estimate_minutes=minutes))

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()

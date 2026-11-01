from datetime import UTC, datetime
from uuid import uuid4

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import Task, User


def create_user(db_session) -> User:
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def test_create_task_with_naive_deadline_returns_422(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.post(
            "/api/v1/tasks/",
            json={"title": "Prepare project", "deadline": "2026-11-10T12:00:00"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


def test_create_task_with_aware_deadline_keeps_the_same_moment(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.post(
            "/api/v1/tasks/",
            json={
                "title": "Prepare project",
                "deadline": "2026-11-10T12:00:00+01:00",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    saved_deadline = datetime.fromisoformat(response.json()["deadline"])
    assert saved_deadline == datetime(2026, 11, 10, 11, 0, tzinfo=UTC)


def test_update_task_with_naive_deadline_returns_422(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="My task")
    db_session.add(task)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"deadline": "2026-11-10T12:00:00"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


def test_update_task_with_aware_deadline_keeps_the_same_moment(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="My task")
    db_session.add(task)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"deadline": "2026-11-10T12:00:00Z"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    saved_deadline = datetime.fromisoformat(response.json()["deadline"])
    assert saved_deadline == datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

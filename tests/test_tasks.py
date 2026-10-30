from uuid import uuid4

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import Subject, Task, User


def create_user(db_session) -> User:
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def create_subject(db_session, user: User) -> Subject:
    subject = Subject(name="Математика", user_id=user.id)
    db_session.add(subject)
    db_session.flush()
    return subject


def test_create_task(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.post(
            "/api/v1/tasks/",
            json={"title": "Prepare project"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    assert response.json()["title"] == "Prepare project"
    assert response.json()["subject_id"] is None


def test_create_task_with_subject(client, db_session):
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.post(
            "/api/v1/tasks/",
            json={
                "title": "Prepare project",
                "subject_id": str(subject.id),
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    assert response.json()["subject_id"] == str(subject.id)


def test_create_task_with_nonexistent_subject_returns_404(
    client,
    db_session,
):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.post(
            "/api/v1/tasks/",
            json={
                "title": "Prepare project",
                "subject_id": str(uuid4()),
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404


def test_create_task_with_another_users_subject_returns_404(
    client,
    db_session,
):
    user = create_user(db_session)
    another_user = create_user(db_session)
    subject = create_subject(db_session, another_user)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.post(
            "/api/v1/tasks/",
            json={
                "title": "Prepare project",
                "subject_id": str(subject.id),
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404


def test_create_task_requires_authentication(client):
    response = client.post(
        "/api/v1/tasks/",
        json={"title": "Prepare project"},
    )
    assert response.status_code in (401, 403)


def test_list_tasks(client, db_session):
    user = create_user(db_session)
    db_session.add(Task(user_id=user.id, title="My task"))
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get("/api/v1/tasks/")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "My task"


def test_get_missing_task_returns_404(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(f"/api/v1/tasks/{uuid4()}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404


def test_update_task(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Old title")
    db_session.add(task)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"title": "New title"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["title"] == "New title"


def test_update_task_can_remove_subject(client, db_session):
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    task = Task(
        user_id=user.id,
        subject_id=subject.id,
        title="Old title",
    )
    db_session.add(task)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"subject_id": None},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["subject_id"] is None


def test_update_task_with_nonexistent_subject_returns_404(
    client,
    db_session,
):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="My task")
    db_session.add(task)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"subject_id": str(uuid4())},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404


def test_update_task_with_another_users_subject_returns_404(
    client,
    db_session,
):
    user = create_user(db_session)
    another_user = create_user(db_session)
    subject = create_subject(db_session, another_user)
    task = Task(user_id=user.id, title="My task")
    db_session.add(task)
    db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"subject_id": str(subject.id)},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404


def test_update_missing_task_returns_404(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{uuid4()}",
            json={"title": "New title"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404


def test_delete_task(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Delete me")
    db_session.add(task)
    db_session.flush()
    task_id = task.id
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.delete(f"/api/v1/tasks/{task_id}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 204
    assert db_session.get(Task, task_id) is None


def test_delete_missing_task_returns_404(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.delete(f"/api/v1/tasks/{uuid4()}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404

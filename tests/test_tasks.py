from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

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


def test_list_tasks_filters_by_status(client, db_session):
    user = create_user(db_session)

    db_session.add_all(
        [
            Task(user_id=user.id, title="Завершить проект", status="completed"),
            Task(user_id=user.id, title="Сделать практику", status="todo"),
            Task(user_id=user.id, title="Продолжить работу", status="in_progress"),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get("/api/v1/tasks/?status=completed")

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["title"] == "Завершить проект"
        assert response.json()[0]["status"] == "completed"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_filters_by_subject(client, db_session):
    user = create_user(db_session)
    math = create_subject(db_session, user)
    history = Subject(name="История", user_id=user.id)
    db_session.add(history)
    db_session.flush()

    db_session.add_all(
        [
            Task(
                user_id=user.id,
                subject_id=math.id,
                title="Решить уравнения",
            ),
            Task(
                user_id=user.id,
                subject_id=history.id,
                title="Прочитать главу",
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(
            "/api/v1/tasks/",
            params={"subject_id": str(math.id)},
        )

        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Решить уравнения"
        assert tasks[0]["subject_id"] == str(math.id)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_sorts_by_created_at_ascending(client, db_session):
    user = create_user(db_session)

    db_session.add_all(
        [
            Task(
                user_id=user.id,
                title="Новая задача",
                created_at=datetime(2026, 10, 3, tzinfo=UTC),
            ),
            Task(
                user_id=user.id,
                title="Старая задача",
                created_at=datetime(2026, 10, 1, tzinfo=UTC),
            ),
            Task(
                user_id=user.id,
                title="Средняя задача",
                created_at=datetime(2026, 10, 2, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(
            "/api/v1/tasks/",
            params={"sort_by": "created_at", "order": "asc"},
        )

        assert response.status_code == 200
        assert [task["title"] for task in response.json()] == [
            "Старая задача",
            "Средняя задача",
            "Новая задача",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_sorts_by_deadline_with_nulls_last(client, db_session):
    user = create_user(db_session)

    db_session.add_all(
        [
            Task(
                user_id=user.id,
                title="Без дедлайна",
                deadline=None,
            ),
            Task(
                user_id=user.id,
                title="Поздний дедлайн",
                deadline=datetime(2026, 11, 10, tzinfo=UTC),
            ),
            Task(
                user_id=user.id,
                title="Ранний дедлайн",
                deadline=datetime(2026, 11, 2, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        ascending = client.get(
            "/api/v1/tasks/",
            params={"sort_by": "deadline", "order": "asc"},
        )
        descending = client.get(
            "/api/v1/tasks/",
            params={"sort_by": "deadline", "order": "desc"},
        )

        assert ascending.status_code == 200
        assert [task["title"] for task in ascending.json()] == [
            "Ранний дедлайн",
            "Поздний дедлайн",
            "Без дедлайна",
        ]

        assert descending.status_code == 200
        assert [task["title"] for task in descending.json()] == [
            "Поздний дедлайн",
            "Ранний дедлайн",
            "Без дедлайна",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_only_returns_current_users_tasks(client, db_session):
    user = create_user(db_session)
    another_user = create_user(db_session)

    db_session.add_all(
        [
            Task(user_id=user.id, title="Моя задача"),
            Task(user_id=another_user.id, title="Чужая задача"),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get("/api/v1/tasks/")

        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Моя задача"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_today_rejects_invalid_date_filter(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "invalid"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_rejects_invalid_sort_by(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(
            "/api/v1/tasks/",
            params={"sort_by": "title"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_rejects_invalid_order(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(
            "/api/v1/tasks/",
            params={"order": "random"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_task_requires_authentication(client):
    response = client.get(f"/api/v1/tasks/{uuid4()}")

    assert response.status_code in (401, 403)


def test_update_task_with_empty_body_returns_422(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Исходная задача")
    db_session.add(task)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={},
        )

        assert response.status_code == 422
        assert "No fields to update" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_task_with_null_title_returns_422(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Исходная задача")
    db_session.add(task)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"title": None},
        )

        assert response.status_code == 422
        assert "Title cannot be null" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_task_with_null_status_returns_422(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Исходная задача")
    db_session.add(task)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"status": None},
        )

        assert response.status_code == 422
        assert "Status cannot be null" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_task_with_invalid_status_returns_422(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Исходная задача")
    db_session.add(task)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"status": "invalid"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_sorts_by_created_at_descending(client, db_session):
    from datetime import datetime

    user = create_user(db_session)

    db_session.add_all(
        [
            Task(
                user_id=user.id,
                title="Старая",
                created_at=datetime(2026, 10, 1, tzinfo=UTC),
            ),
            Task(
                user_id=user.id,
                title="Новая",
                created_at=datetime(2026, 10, 3, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(
            "/api/v1/tasks/",
            params={"sort_by": "created_at", "order": "desc"},
        )

        assert response.status_code == 200
        assert [task["title"] for task in response.json()] == [
            "Новая",
            "Старая",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_task_with_invalid_status_is_rejected(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Исходная задача")
    db_session.add(task)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"status": "invalid"},
        )

        assert response.status_code == 422
        assert "status" in response.text.lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_task_with_empty_body_does_not_change_task(client, db_session):
    user = create_user(db_session)
    task = Task(user_id=user.id, title="Не менять", status="todo")
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.patch(
            f"/api/v1/tasks/{task_id}",
            json={},
        )

        assert response.status_code == 422

        db_session.refresh(task)
        assert task.title == "Не менять"
        assert task.status == "todo"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_today_includes_tasks_due_today(client, db_session):
    """Tasks with deadlines today are included in the today filter."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        timezone = ZoneInfo(user.timezone)
        today = datetime.now(timezone).date()
        deadline = datetime.combine(
            today,
            time(hour=12),
            tzinfo=timezone,
        )

        task = Task(
            user_id=user.id,
            title="Task due today",
            deadline=deadline,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/?date_filter=today")

        assert response.status_code == 200
        task_ids = {item["id"] for item in response.json()}
        assert str(task.id) in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_today_excludes_tasks_due_tomorrow(client, db_session):
    """Tasks with deadlines tomorrow are excluded from the today filter."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        timezone = ZoneInfo(user.timezone)
        tomorrow = datetime.now(timezone).date() + timedelta(days=1)
        deadline = datetime.combine(
            tomorrow,
            time(hour=12),
            tzinfo=timezone,
        )

        task = Task(
            user_id=user.id,
            title="Task due tomorrow",
            deadline=deadline,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/?date_filter=today")

        assert response.status_code == 200
        task_ids = {item["id"] for item in response.json()}
        assert str(task.id) not in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_today_excludes_tasks_without_deadline(client, db_session):
    """Tasks without deadlines are excluded from the today filter."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        task = Task(
            user_id=user.id,
            title="Task without deadline",
            deadline=None,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/?date_filter=today")

        assert response.status_code == 200
        task_ids = {item["id"] for item in response.json()}
        assert str(task.id) not in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_today_rejects_invalid_date_filter(client, db_session):
    """Unsupported date filter values return 422."""
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "invalid"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_overdue_includes_uncompleted_past_deadline(
    client,
    db_session,
):
    """Overdue filter includes uncompleted tasks with past deadlines."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        deadline = datetime.now(ZoneInfo(user.timezone)) - timedelta(days=1)
        task = Task(
            user_id=user.id,
            title="Overdue task",
            deadline=deadline,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/?date_filter=overdue")

        assert response.status_code == 200
        assert str(task.id) in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_overdue_excludes_completed_tasks(client, db_session):
    """Overdue filter excludes completed tasks."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        deadline = datetime.now(ZoneInfo(user.timezone)) - timedelta(days=1)
        task = Task(
            user_id=user.id,
            title="Completed task",
            deadline=deadline,
            status="completed",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/?date_filter=overdue")

        assert response.status_code == 200
        assert str(task.id) not in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_upcoming_includes_future_deadline(client, db_session):
    """Upcoming filter includes tasks with future deadlines."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        deadline = datetime.now(ZoneInfo(user.timezone)) + timedelta(days=1)
        task = Task(
            user_id=user.id,
            title="Upcoming task",
            deadline=deadline,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/?date_filter=upcoming")

        assert response.status_code == 200
        assert str(task.id) in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_upcoming_excludes_completed_tasks(client, db_session):
    """Upcoming filter excludes completed tasks."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        deadline = datetime.now(ZoneInfo(user.timezone)) + timedelta(days=1)
        task = Task(
            user_id=user.id,
            title="Completed future task",
            deadline=deadline,
            status="completed",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/?date_filter=upcoming")

        assert response.status_code == 200
        assert str(task.id) not in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_combines_status_and_overdue_filters(client, db_session):
    """Status and overdue filters are applied together."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        deadline = datetime.now(ZoneInfo(user.timezone)) - timedelta(days=1)

        todo_task = Task(
            user_id=user.id,
            title="Overdue todo task",
            deadline=deadline,
            status="todo",
        )
        in_progress_task = Task(
            user_id=user.id,
            title="Overdue in-progress task",
            deadline=deadline,
            status="in_progress",
        )

        db_session.add_all([todo_task, in_progress_task])
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={
                "status": "todo",
                "date_filter": "overdue",
            },
        )

        assert response.status_code == 200
        task_ids = {item["id"] for item in response.json()}

        assert str(todo_task.id) in task_ids
        assert str(in_progress_task.id) not in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_overdue_excludes_future_deadlines(client, db_session):
    """Overdue filter excludes tasks whose deadlines are in the future."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        task = Task(
            user_id=user.id,
            title="Future task",
            deadline=datetime.now(ZoneInfo(user.timezone)) + timedelta(days=1),
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "overdue"},
        )

        assert response.status_code == 200
        assert str(task.id) not in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_upcoming_excludes_past_deadlines(client, db_session):
    """Upcoming filter excludes tasks whose deadlines have passed."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        task = Task(
            user_id=user.id,
            title="Past task",
            deadline=datetime.now(ZoneInfo(user.timezone)) - timedelta(days=1),
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "upcoming"},
        )

        assert response.status_code == 200
        assert str(task.id) not in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_overdue_excludes_tasks_without_deadlines(
    client,
    db_session,
):
    """Overdue filter excludes tasks without deadlines."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        task = Task(
            user_id=user.id,
            title="No deadline",
            deadline=None,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "overdue"},
        )

        assert response.status_code == 200
        assert str(task.id) not in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_upcoming_excludes_tasks_without_deadlines(
    client,
    db_session,
):
    """Upcoming filter excludes tasks without deadlines."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        task = Task(
            user_id=user.id,
            title="No deadline",
            deadline=None,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "upcoming"},
        )

        assert response.status_code == 200
        assert str(task.id) not in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_combines_status_and_upcoming_filters(
    client,
    db_session,
):
    """Status and upcoming filters are applied together."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        deadline = datetime.now(ZoneInfo(user.timezone)) + timedelta(days=1)

        todo_task = Task(
            user_id=user.id,
            title="Upcoming todo",
            deadline=deadline,
            status="todo",
        )
        in_progress_task = Task(
            user_id=user.id,
            title="Upcoming in progress",
            deadline=deadline,
            status="in_progress",
        )
        db_session.add_all([todo_task, in_progress_task])
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"status": "todo", "date_filter": "upcoming"},
        )

        assert response.status_code == 200
        task_ids = {item["id"] for item in response.json()}
        assert str(todo_task.id) in task_ids
        assert str(in_progress_task.id) not in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_combines_status_and_today_filters(
    client,
    db_session,
):
    """Status and today filters are applied together."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        timezone = ZoneInfo(user.timezone)
        today = datetime.now(timezone).date()
        deadline = datetime.combine(
            today,
            time(hour=12),
            tzinfo=timezone,
        )

        todo_task = Task(
            user_id=user.id,
            title="Today's todo",
            deadline=deadline,
            status="todo",
        )
        completed_task = Task(
            user_id=user.id,
            title="Today's completed task",
            deadline=deadline,
            status="completed",
        )
        db_session.add_all([todo_task, completed_task])
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"status": "todo", "date_filter": "today"},
        )

        assert response.status_code == 200
        task_ids = {item["id"] for item in response.json()}
        assert str(todo_task.id) in task_ids
        assert str(completed_task.id) not in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_date_filter_does_not_return_another_users_tasks(
    client,
    db_session,
):
    """Date filters return only tasks owned by the authenticated user."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    another_user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        deadline = datetime.now(ZoneInfo(user.timezone)) + timedelta(days=1)
        another_users_task = Task(
            user_id=another_user.id,
            title="Another user's task",
            deadline=deadline,
            status="todo",
        )
        db_session.add(another_users_task)
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "upcoming"},
        )

        assert response.status_code == 200
        task_ids = {item["id"] for item in response.json()}
        assert str(another_users_task.id) not in task_ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_without_date_filter_includes_tasks_without_deadlines(
    client,
    db_session,
):
    """Omitting date_filter does not exclude tasks without deadlines."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        task = Task(
            user_id=user.id,
            title="Task without deadline",
            deadline=None,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get("/api/v1/tasks/")

        assert response.status_code == 200
        assert str(task.id) in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_today_includes_deadline_at_start_of_day(
    client,
    db_session,
):
    """Today filter includes a task due exactly at local midnight."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        timezone = ZoneInfo(user.timezone)
        today = datetime.now(timezone).date()
        deadline = datetime.combine(today, time.min, tzinfo=timezone)

        task = Task(
            user_id=user.id,
            title="Task at start of day",
            deadline=deadline,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "today"},
        )

        assert response.status_code == 200
        assert str(task.id) in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_today_excludes_deadline_at_start_of_next_day(
    client,
    db_session,
):
    """Today filter excludes a task due exactly at next local midnight."""
    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        timezone = ZoneInfo(user.timezone)
        tomorrow = datetime.now(timezone).date() + timedelta(days=1)
        deadline = datetime.combine(tomorrow, time.min, tzinfo=timezone)

        task = Task(
            user_id=user.id,
            title="Task at next day's start",
            deadline=deadline,
            status="todo",
        )
        db_session.add(task)
        db_session.commit()

        response = client.get(
            "/api/v1/tasks/",
            params={"date_filter": "today"},
        )

        assert response.status_code == 200
        assert str(task.id) not in {item["id"] for item in response.json()}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_sorts_by_created_at_desc(client, db_session):
    """По умолчанию новые задачи должны идти первыми."""
    from datetime import UTC, datetime, timedelta

    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        older = Task(
            user_id=user.id,
            title="Older task",
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
        newer = Task(
            user_id=user.id,
            title="Newer task",
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
        db_session.add_all([older, newer])
        db_session.commit()

        response = client.get("/api/v1/tasks")

        assert response.status_code == 200
        tasks = response.json()
        assert [task["title"] for task in tasks] == [
            "Newer task",
            "Older task",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_sorts_by_created_at_asc(client, db_session):
    """При asc сначала идут старые задачи."""
    from datetime import UTC, datetime, timedelta

    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        older = Task(
            user_id=user.id,
            title="Older task",
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
        newer = Task(
            user_id=user.id,
            title="Newer task",
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
        db_session.add_all([older, newer])
        db_session.commit()

        response = client.get(
            "/api/v1/tasks",
            params={"sort_by": "created_at", "order": "asc"},
        )

        assert response.status_code == 200
        assert [task["title"] for task in response.json()] == [
            "Older task",
            "Newer task",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_sorts_by_deadline_asc(client, db_session):
    """Сначала должны идти задачи с ближайшим дедлайном."""
    from datetime import UTC, datetime, timedelta

    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        later = Task(
            user_id=user.id,
            title="Later deadline",
            deadline=datetime.now(UTC) + timedelta(days=3),
        )
        sooner = Task(
            user_id=user.id,
            title="Sooner deadline",
            deadline=datetime.now(UTC) + timedelta(days=1),
        )
        db_session.add_all([later, sooner])
        db_session.commit()

        response = client.get(
            "/api/v1/tasks",
            params={"sort_by": "deadline", "order": "asc"},
        )

        assert response.status_code == 200
        assert [task["title"] for task in response.json()] == [
            "Sooner deadline",
            "Later deadline",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_sorts_by_deadline_desc(client, db_session):
    """При desc сначала должен идти самый поздний дедлайн."""
    from datetime import UTC, datetime, timedelta

    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        earlier = Task(
            user_id=user.id,
            title="Earlier deadline",
            deadline=datetime.now(UTC) + timedelta(days=1),
        )
        later = Task(
            user_id=user.id,
            title="Later deadline",
            deadline=datetime.now(UTC) + timedelta(days=3),
        )
        db_session.add_all([earlier, later])
        db_session.commit()

        response = client.get(
            "/api/v1/tasks",
            params={"sort_by": "deadline", "order": "desc"},
        )

        assert response.status_code == 200
        assert [task["title"] for task in response.json()] == [
            "Later deadline",
            "Earlier deadline",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_deadline_sort_places_missing_deadlines_last(client, db_session):
    """Задачи без дедлайна должны оставаться в конце списка."""
    from datetime import UTC, datetime, timedelta

    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        no_deadline = Task(
            user_id=user.id,
            title="No deadline",
            deadline=None,
        )
        with_deadline = Task(
            user_id=user.id,
            title="Has deadline",
            deadline=datetime.now(UTC) + timedelta(days=1),
        )
        db_session.add_all([no_deadline, with_deadline])
        db_session.commit()

        for order in ("asc", "desc"):
            response = client.get(
                "/api/v1/tasks",
                params={"sort_by": "deadline", "order": order},
            )

            assert response.status_code == 200
            titles = [task["title"] for task in response.json()]
            assert titles[-1] == "No deadline"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_combines_overdue_filter_with_deadline_sort(client, db_session):
    """Сортировка должна применяться после фильтрации просроченных задач."""
    from datetime import UTC, datetime, timedelta

    from studyflow.models.task import Task

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        older_deadline = Task(
            user_id=user.id,
            title="Older deadline",
            deadline=datetime.now(UTC) - timedelta(days=3),
        )
        newer_deadline = Task(
            user_id=user.id,
            title="Newer deadline",
            deadline=datetime.now(UTC) - timedelta(days=1),
        )
        future = Task(
            user_id=user.id,
            title="Future deadline",
            deadline=datetime.now(UTC) + timedelta(days=2),
        )
        db_session.add_all([older_deadline, newer_deadline, future])
        db_session.commit()

        response = client.get(
            "/api/v1/tasks",
            params={
                "date_filter": "overdue",
                "sort_by": "deadline",
                "order": "asc",
            },
        )

        assert response.status_code == 200
        assert [task["title"] for task in response.json()] == [
            "Older deadline",
            "Newer deadline",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_rejects_invalid_sort_by(client, db_session):
    """Неизвестное поле сортировки должно возвращать 422."""
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.get(
            "/api/v1/tasks",
            params={"sort_by": "title"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_tasks_rejects_invalid_order(client, db_session):
    """Неизвестное направление сортировки должно возвращать 422."""
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.get(
            "/api/v1/tasks",
            params={"order": "sideways"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_nonexistent_task_returns_404(client, db_session):
    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.delete(
            f"/api/v1/tasks/{uuid4()}",
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Task not found"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_task_returns_task(client, db_session):
    from studyflow.models.task import Task

    user = create_user(db_session)
    task = Task(
        user_id=user.id,
        title="Test task",
        status="todo",
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(f"/api/v1/tasks/{task_id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(task_id)
        assert response.json()["title"] == "Test task"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_create_task_rolls_back_on_commit_error(client, db_session, monkeypatch):
    from unittest.mock import Mock

    user = create_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    rollback = Mock()
    test_client = TestClient(app, raise_server_exceptions=False)

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)

    try:
        response = test_client.post(
            "/api/v1/tasks/",
            json={
                "title": "Test task",
                "description": "Test description",
                "subject_id": None,
                "deadline": None,
                "status": "todo",
            },
        )

        assert response.status_code == 500
        rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_task_rolls_back_on_commit_error(client, db_session, monkeypatch):
    from unittest.mock import Mock

    from studyflow.models.task import Task

    user = create_user(db_session)
    task = Task(
        user_id=user.id,
        title="Original title",
        status="todo",
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    app.dependency_overrides[get_current_user] = lambda: user
    rollback = Mock()
    test_client = TestClient(app, raise_server_exceptions=False)

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)

    try:
        response = test_client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"title": "Updated title"},
        )

        assert response.status_code == 500
        rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_task_rolls_back_on_commit_error(client, db_session, monkeypatch):
    from unittest.mock import Mock

    from studyflow.models.task import Task

    user = create_user(db_session)
    task = Task(
        user_id=user.id,
        title="Task to delete",
        status="todo",
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    app.dependency_overrides[get_current_user] = lambda: user
    rollback = Mock()
    test_client = TestClient(app, raise_server_exceptions=False)

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)

    try:
        response = test_client.delete(f"/api/v1/tasks/{task_id}")

        assert response.status_code == 500
        rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)

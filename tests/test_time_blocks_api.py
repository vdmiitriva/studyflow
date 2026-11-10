from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import Subject, Task, TimeBlock, User

BLOCKS_URL = "/api/v1/blocks/"
TASKS_URL = "/api/v1/tasks/"
SUBJECTS_URL = "/api/v1/subjects/"

START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def at(hours: float) -> datetime:
    """A moment `hours` after START (09:00 UTC); negative means before."""
    return START + timedelta(hours=hours)


def make_user(db_session) -> User:
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def user(db_session):
    current_user = make_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: current_user
    yield current_user
    app.dependency_overrides.pop(get_current_user, None)


def add_task(db_session, user: User, **fields) -> Task:
    task = Task(user_id=user.id, title=fields.pop("title", "Lab report"), **fields)
    db_session.add(task)
    db_session.flush()
    return task


def add_subject(db_session, user: User) -> Subject:
    subject = Subject(name="Physics", user_id=user.id)
    db_session.add(subject)
    db_session.flush()
    return subject


def add_block(db_session, user: User, start=START, end=None, **fields) -> TimeBlock:
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


def payload(start=START, end=None, **fields) -> dict:
    body = {
        "title": "Study",
        "starts_at": start.isoformat(),
        "ends_at": (end or start + timedelta(hours=1)).isoformat(),
    }
    body.update(fields)
    return body


def period(start: datetime, end: datetime) -> dict[str, str]:
    return {"from": start.isoformat(), "to": end.isoformat()}


def count_blocks(db_session, user: User) -> int:
    query = select(func.count()).select_from(TimeBlock)
    query = query.where(TimeBlock.user_id == user.id)
    return db_session.execute(query).scalar_one()


def block_url(block) -> str:
    return f"{BLOCKS_URL}{block.id}"


# ---------- creating a block ----------


def test_create_standalone_block(client, user):
    response = client.post(BLOCKS_URL, json=payload())

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Study"
    assert data["status"] == "planned"
    assert data["task_id"] is None
    assert data["subject_id"] is None
    assert data["conflicting_block_ids"] == []
    assert datetime.fromisoformat(data["starts_at"]) == START


def test_block_title_defaults_to_the_task_title(client, db_session, user):
    task = add_task(db_session, user, title="Lab report")
    body = payload(task_id=str(task.id))
    del body["title"]

    response = client.post(BLOCKS_URL, json=body)

    assert response.status_code == 201
    assert response.json()["title"] == "Lab report"
    assert response.json()["task_id"] == str(task.id)


def test_explicit_title_wins_over_the_task_title(client, db_session, user):
    task = add_task(db_session, user, title="Lab report")

    response = client.post(BLOCKS_URL, json=payload(task_id=str(task.id)))

    assert response.status_code == 201
    assert response.json()["title"] == "Study"


def test_create_block_with_a_subject(client, db_session, user):
    subject = add_subject(db_session, user)

    response = client.post(BLOCKS_URL, json=payload(subject_id=str(subject.id)))

    assert response.status_code == 201
    assert response.json()["subject_id"] == str(subject.id)


def test_one_task_can_get_several_blocks(client, db_session, user):
    task = add_task(db_session, user)

    for day in range(3):
        response = client.post(
            BLOCKS_URL,
            json=payload(start=at(24 * day), task_id=str(task.id)),
        )
        assert response.status_code == 201

    assert count_blocks(db_session, user) == 3


def test_title_is_trimmed(client, user):
    response = client.post(BLOCKS_URL, json=payload(title="  Study  "))

    assert response.status_code == 201
    assert response.json()["title"] == "Study"


@pytest.mark.parametrize("title", ["   ", "", "x" * 201])
def test_create_block_rejects_bad_title(client, user, title):
    response = client.post(BLOCKS_URL, json=payload(title=title))

    assert response.status_code == 422


def test_block_without_title_and_task_is_rejected(client, user):
    body = payload()
    del body["title"]

    response = client.post(BLOCKS_URL, json=body)

    assert response.status_code == 422


def test_block_cannot_have_task_and_subject_together(client, db_session, user):
    task = add_task(db_session, user)
    subject = add_subject(db_session, user)

    response = client.post(
        BLOCKS_URL,
        json=payload(task_id=str(task.id), subject_id=str(subject.id)),
    )

    assert response.status_code == 422


@pytest.mark.parametrize("end", [0, -1])
def test_block_must_end_after_it_starts(client, user, end):
    response = client.post(BLOCKS_URL, json=payload(end=at(end)))

    assert response.status_code == 422


def test_create_block_rejects_time_without_timezone(client, user):
    body = {
        "title": "Study",
        "starts_at": "2026-11-10T09:00:00",
        "ends_at": "2026-11-10T10:00:00+00:00",
    }

    response = client.post(BLOCKS_URL, json=body)

    assert response.status_code == 422


@pytest.mark.parametrize("status", ["done", "banana", None])
def test_create_block_rejects_unknown_status(client, user, status):
    response = client.post(BLOCKS_URL, json=payload(status=status))

    assert response.status_code == 422


def test_create_block_with_unknown_task_returns_404(client, user):
    response = client.post(BLOCKS_URL, json=payload(task_id=str(uuid4())))

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_create_block_with_another_users_task_returns_404(client, db_session, user):
    foreign_task = add_task(db_session, make_user(db_session))

    response = client.post(BLOCKS_URL, json=payload(task_id=str(foreign_task.id)))

    assert response.status_code == 404


def test_create_block_with_unknown_subject_returns_404(client, user):
    response = client.post(BLOCKS_URL, json=payload(subject_id=str(uuid4())))

    assert response.status_code == 404
    assert response.json()["detail"] == "Subject not found"


def test_create_block_with_another_users_subject_returns_404(client, db_session, user):
    foreign_subject = add_subject(db_session, make_user(db_session))

    response = client.post(
        BLOCKS_URL,
        json=payload(subject_id=str(foreign_subject.id)),
    )

    assert response.status_code == 404


def test_create_block_requires_authentication(client):
    response = client.post(BLOCKS_URL, json=payload())

    assert response.status_code == 401


# ---------- conflicts when creating ----------


def test_overlapping_block_returns_409_and_is_not_saved(client, db_session, user):
    existing = add_block(db_session, user, title="Lecture")

    response = client.post(BLOCKS_URL, json=payload(start=at(0.5), end=at(1.5)))

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert [item["id"] for item in detail["conflicts"]] == [str(existing.id)]
    assert detail["conflicts"][0]["title"] == "Lecture"
    assert count_blocks(db_session, user) == 1


def test_overlapping_block_is_saved_when_the_user_confirms(client, db_session, user):
    existing = add_block(db_session, user)

    response = client.post(
        BLOCKS_URL,
        params={"allow_conflicts": "true"},
        json=payload(start=at(0.5), end=at(1.5)),
    )

    assert response.status_code == 201
    assert response.json()["conflicting_block_ids"] == [str(existing.id)]
    assert count_blocks(db_session, user) == 2


@pytest.mark.parametrize(("start", "end"), [(-1, 0), (1, 2)])
def test_blocks_that_only_touch_do_not_conflict(client, db_session, user, start, end):
    add_block(db_session, user)

    response = client.post(BLOCKS_URL, json=payload(start=at(start), end=at(end)))

    assert response.status_code == 201
    assert response.json()["conflicting_block_ids"] == []


@pytest.mark.parametrize("status", ["skipped", "completed"])
def test_finished_or_skipped_blocks_do_not_conflict(client, db_session, user, status):
    add_block(db_session, user, status=status)

    response = client.post(BLOCKS_URL, json=payload(start=at(0.5), end=at(1.5)))

    assert response.status_code == 201


def test_another_users_block_does_not_conflict(client, db_session, user):
    add_block(db_session, make_user(db_session))

    response = client.post(BLOCKS_URL, json=payload())

    assert response.status_code == 201


@pytest.mark.parametrize("status", ["completed", "skipped"])
def test_conflicts_are_not_checked_for_non_planned_blocks(
    client, db_session, user, status
):
    add_block(db_session, user)

    response = client.post(BLOCKS_URL, json=payload(status=status))

    assert response.status_code == 201
    assert response.json()["conflicting_block_ids"] == []


def test_conflict_warning_lists_at_most_ten_blocks(client, db_session, user):
    for number in range(12):
        add_block(db_session, user, title=f"Block {number}")

    response = client.post(BLOCKS_URL, json=payload())

    assert response.status_code == 409
    assert len(response.json()["detail"]["conflicts"]) == 10


# ---------- blocks of a calendar period ----------


def test_list_returns_blocks_of_the_period_in_order(client, db_session, user):
    add_block(db_session, user, title="Later", start=at(5))
    add_block(db_session, user, title="Earlier", start=at(0))
    add_block(db_session, user, title="Next week", start=at(24 * 7))

    response = client.get(BLOCKS_URL, params=period(at(-1), at(10)))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Earlier", "Later"]


def test_block_crossing_midnight_is_listed_on_both_days(client, db_session, user):
    block = add_block(
        db_session,
        user,
        start=datetime(2026, 11, 6, 23, 0, tzinfo=UTC),
        end=datetime(2026, 11, 7, 1, 0, tzinfo=UTC),
    )

    def ids_on(day: int) -> list[str]:
        day_start = datetime(2026, 11, day, 0, 0, tzinfo=UTC)
        response = client.get(
            BLOCKS_URL,
            params=period(day_start, day_start + timedelta(days=1)),
        )
        return [item["id"] for item in response.json()]

    assert ids_on(6) == [str(block.id)]
    assert ids_on(7) == [str(block.id)]
    assert ids_on(8) == []


def test_blocks_touching_the_period_edges_are_not_listed(client, db_session, user):
    add_block(db_session, user, title="Ends at start", start=at(-2), end=at(0))
    add_block(db_session, user, title="Starts at end", start=at(3))
    inside = add_block(db_session, user, title="Inside", start=at(1))

    response = client.get(BLOCKS_URL, params=period(at(0), at(3)))

    assert [item["id"] for item in response.json()] == [str(inside.id)]


def test_list_marks_conflicting_planned_blocks(client, db_session, user):
    first = add_block(db_session, user, title="A", start=at(0), end=at(2))
    second = add_block(db_session, user, title="B", start=at(1), end=at(3))
    alone = add_block(db_session, user, title="C", start=at(5))
    skipped = add_block(db_session, user, title="S", start=at(1), status="skipped")

    response = client.get(BLOCKS_URL, params=period(at(-1), at(10)))

    found = {item["id"]: item["conflicting_block_ids"] for item in response.json()}
    assert found[str(first.id)] == [str(second.id)]
    assert found[str(second.id)] == [str(first.id)]
    assert found[str(alone.id)] == []
    assert found[str(skipped.id)] == []


def test_list_returns_only_the_current_users_blocks(client, db_session, user):
    mine = add_block(db_session, user)
    add_block(db_session, make_user(db_session))

    response = client.get(BLOCKS_URL, params=period(at(-1), at(10)))

    assert [item["id"] for item in response.json()] == [str(mine.id)]


@pytest.mark.parametrize(
    ("start", "end"),
    [(0, 0), (1, 0), (0, 24 * 62 + 1)],
)
def test_list_rejects_a_bad_period(client, user, start, end):
    response = client.get(BLOCKS_URL, params=period(at(start), at(end)))

    assert response.status_code == 422


def test_list_accepts_a_period_of_62_days(client, user):
    response = client.get(BLOCKS_URL, params=period(at(0), at(24 * 62)))

    assert response.status_code == 200


@pytest.mark.parametrize("params", [{}, {"from": "2026-11-10T00:00:00+00:00"}])
def test_list_requires_both_ends_of_the_period(client, user, params):
    response = client.get(BLOCKS_URL, params=params)

    assert response.status_code == 422


def test_list_rejects_a_period_without_timezone(client, user):
    params = {"from": "2026-11-10T00:00:00", "to": "2026-11-11T00:00:00+00:00"}

    response = client.get(BLOCKS_URL, params=params)

    assert response.status_code == 422


def test_list_requires_authentication(client):
    response = client.get(BLOCKS_URL, params=period(at(0), at(10)))

    assert response.status_code == 401


# ---------- reading one block ----------


def test_get_block_shows_its_conflicts(client, db_session, user):
    block = add_block(db_session, user)
    other = add_block(db_session, user, start=at(0.5))

    response = client.get(block_url(block))

    assert response.status_code == 200
    assert response.json()["id"] == str(block.id)
    assert response.json()["conflicting_block_ids"] == [str(other.id)]


def test_completed_block_has_no_conflicts(client, db_session, user):
    block = add_block(db_session, user, status="completed")
    add_block(db_session, user, start=at(0.5))

    response = client.get(block_url(block))

    assert response.json()["conflicting_block_ids"] == []


def test_get_missing_block_returns_404(client, user):
    response = client.get(f"{BLOCKS_URL}{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Block not found"


def test_get_another_users_block_returns_404(client, db_session, user):
    foreign_block = add_block(db_session, make_user(db_session))

    response = client.get(block_url(foreign_block))

    assert response.status_code == 404


# ---------- updating a block ----------


def test_update_title_and_status(client, db_session, user):
    block = add_block(db_session, user)

    response = client.patch(
        block_url(block),
        json={"title": "New title", "status": "completed"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "New title"
    db_session.refresh(block)
    assert block.status == "completed"


def test_moving_a_block_into_a_conflict_returns_409(client, db_session, user):
    add_block(db_session, user, start=at(0))
    block = add_block(db_session, user, start=at(2))

    response = client.patch(
        block_url(block),
        json={"starts_at": at(0.5).isoformat(), "ends_at": at(1.5).isoformat()},
    )

    assert response.status_code == 409
    db_session.refresh(block)
    assert block.starts_at == at(2)


def test_moving_a_block_into_a_conflict_works_when_confirmed(client, db_session, user):
    existing = add_block(db_session, user, start=at(0))
    block = add_block(db_session, user, start=at(2))

    response = client.patch(
        block_url(block),
        params={"allow_conflicts": "true"},
        json={"starts_at": at(0.5).isoformat(), "ends_at": at(1.5).isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["conflicting_block_ids"] == [str(existing.id)]


def test_a_block_does_not_conflict_with_itself(client, db_session, user):
    block = add_block(db_session, user)

    response = client.patch(block_url(block), json={"ends_at": at(1.5).isoformat()})

    assert response.status_code == 200
    assert response.json()["conflicting_block_ids"] == []


def test_renaming_a_block_that_is_already_in_conflict_is_allowed(
    client, db_session, user
):
    first = add_block(db_session, user, start=at(0), end=at(2))
    second = add_block(db_session, user, start=at(1), end=at(3))

    response = client.patch(block_url(first), json={"title": "Renamed"})

    assert response.status_code == 200
    assert response.json()["conflicting_block_ids"] == [str(second.id)]


def test_completing_a_conflicting_block_needs_no_confirmation(client, db_session, user):
    first = add_block(db_session, user, start=at(0), end=at(2))
    add_block(db_session, user, start=at(1), end=at(3))

    response = client.patch(block_url(first), json={"status": "completed"})

    assert response.status_code == 200
    assert response.json()["conflicting_block_ids"] == []


def test_reviving_a_skipped_block_checks_conflicts(client, db_session, user):
    existing = add_block(db_session, user, start=at(0))
    skipped = add_block(db_session, user, start=at(0.5), status="skipped")

    refused = client.patch(block_url(skipped), json={"status": "planned"})
    confirmed = client.patch(
        block_url(skipped),
        params={"allow_conflicts": "true"},
        json={"status": "planned"},
    )

    assert refused.status_code == 409
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "planned"
    assert confirmed.json()["conflicting_block_ids"] == [str(existing.id)]


def test_update_both_ends_of_a_block(client, db_session, user):
    block = add_block(db_session, user)

    response = client.patch(
        block_url(block),
        json={"starts_at": at(3).isoformat(), "ends_at": at(4).isoformat()},
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["starts_at"]) == at(3)


def test_update_rejects_a_reversed_pair(client, db_session, user):
    block = add_block(db_session, user)

    response = client.patch(
        block_url(block),
        json={"starts_at": at(4).isoformat(), "ends_at": at(3).isoformat()},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "change",
    [{"ends_at": at(-1).isoformat()}, {"starts_at": at(2).isoformat()}],
)
def test_update_cannot_make_the_stored_block_end_before_it_starts(
    client, db_session, user, change
):
    block = add_block(db_session, user)

    response = client.patch(block_url(block), json=change)

    assert response.status_code == 422
    assert response.json()["detail"] == "Block must end after it starts"


def test_update_cannot_add_a_task_to_a_block_with_a_subject(client, db_session, user):
    subject = add_subject(db_session, user)
    block = add_block(db_session, user, subject_id=subject.id)
    task = add_task(db_session, user)

    response = client.patch(block_url(block), json={"task_id": str(task.id)})

    assert response.status_code == 422
    assert response.json()["detail"] == "A block cannot have both a task and a subject"


def test_update_rejects_task_and_subject_in_one_request(client, db_session, user):
    block = add_block(db_session, user)
    task = add_task(db_session, user)
    subject = add_subject(db_session, user)

    response = client.patch(
        block_url(block),
        json={"task_id": str(task.id), "subject_id": str(subject.id)},
    )

    assert response.status_code == 422


def test_a_subject_can_be_replaced_by_a_task_in_one_request(client, db_session, user):
    subject = add_subject(db_session, user)
    block = add_block(db_session, user, subject_id=subject.id)
    task = add_task(db_session, user)

    response = client.patch(
        block_url(block),
        json={"task_id": str(task.id), "subject_id": None},
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == str(task.id)
    assert response.json()["subject_id"] is None


def test_a_block_can_be_detached_from_its_task(client, db_session, user):
    task = add_task(db_session, user)
    block = add_block(db_session, user, task_id=task.id, title="Keep me")

    response = client.patch(block_url(block), json={"task_id": None})

    assert response.status_code == 200
    assert response.json()["task_id"] is None
    assert response.json()["title"] == "Keep me"


def test_update_with_another_users_task_returns_404(client, db_session, user):
    block = add_block(db_session, user)
    foreign_task = add_task(db_session, make_user(db_session))

    response = client.patch(block_url(block), json={"task_id": str(foreign_task.id)})

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_update_with_unknown_subject_returns_404(client, db_session, user):
    block = add_block(db_session, user)

    response = client.patch(block_url(block), json={"subject_id": str(uuid4())})

    assert response.status_code == 404
    assert response.json()["detail"] == "Subject not found"


@pytest.mark.parametrize("field", ["title", "starts_at", "ends_at", "status"])
def test_update_rejects_null_for_required_fields(client, db_session, user, field):
    block = add_block(db_session, user)

    response = client.patch(block_url(block), json={field: None})

    assert response.status_code == 422


def test_update_rejects_an_empty_body(client, db_session, user):
    block = add_block(db_session, user)

    response = client.patch(block_url(block), json={})

    assert response.status_code == 422


def test_update_rejects_an_unknown_status(client, db_session, user):
    block = add_block(db_session, user)

    response = client.patch(block_url(block), json={"status": "done"})

    assert response.status_code == 422


def test_update_missing_block_returns_404(client, user):
    response = client.patch(f"{BLOCKS_URL}{uuid4()}", json={"title": "New"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Block not found"


def test_update_another_users_block_returns_404(client, db_session, user):
    foreign_block = add_block(db_session, make_user(db_session))

    response = client.patch(block_url(foreign_block), json={"title": "Mine now"})

    assert response.status_code == 404


# ---------- deleting ----------


def test_delete_block(client, db_session, user):
    block = add_block(db_session, user)

    response = client.delete(block_url(block))

    assert response.status_code == 204
    assert count_blocks(db_session, user) == 0


def test_delete_missing_block_returns_404(client, user):
    response = client.delete(f"{BLOCKS_URL}{uuid4()}")

    assert response.status_code == 404


def test_delete_another_users_block_returns_404(client, db_session, user):
    foreign_block = add_block(db_session, make_user(db_session))

    response = client.delete(block_url(foreign_block))

    assert response.status_code == 404


def test_deleting_a_task_deletes_its_blocks(client, db_session, user):
    task = add_task(db_session, user)
    add_block(db_session, user, task_id=task.id)
    add_block(db_session, user)

    response = client.delete(f"{TASKS_URL}{task.id}")

    assert response.status_code == 204
    assert count_blocks(db_session, user) == 1


def test_a_subject_with_blocks_cannot_be_deleted(client, db_session, user):
    subject = add_subject(db_session, user)
    add_block(db_session, user, subject_id=subject.id)

    response = client.delete(f"{SUBJECTS_URL}{subject.id}")

    assert response.status_code == 409


# ---------- database errors ----------


def break_commit(db_session, monkeypatch) -> Mock:
    def fail_commit():
        raise RuntimeError("Database commit failed")

    rollback = Mock()
    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)
    return rollback


def test_create_block_rolls_back_on_commit_error(client, db_session, user, monkeypatch):
    rollback = break_commit(db_session, monkeypatch)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post(BLOCKS_URL, json=payload())

    assert response.status_code == 500
    rollback.assert_called_once()


def test_update_block_rolls_back_on_commit_error(client, db_session, user, monkeypatch):
    block = add_block(db_session, user)
    rollback = break_commit(db_session, monkeypatch)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.patch(block_url(block), json={"title": "New"})

    assert response.status_code == 500
    rollback.assert_called_once()


def test_delete_block_rolls_back_on_commit_error(client, db_session, user, monkeypatch):
    block = add_block(db_session, user)
    rollback = break_commit(db_session, monkeypatch)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.delete(block_url(block))

    assert response.status_code == 500
    rollback.assert_called_once()

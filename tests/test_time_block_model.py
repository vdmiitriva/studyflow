from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from studyflow.models import Subject, Task, TimeBlock, User

START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


def make_user(db_session) -> User:
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def make_subject(db_session, user: User) -> Subject:
    subject = Subject(name="Physics", user_id=user.id)
    db_session.add(subject)
    db_session.flush()
    return subject


def make_task(db_session, user: User) -> Task:
    task = Task(user_id=user.id, title="Lab report")
    db_session.add(task)
    db_session.flush()
    return task


def block_for(user: User, **fields) -> TimeBlock:
    values = {"title": "Block", "starts_at": START, "ends_at": END}
    values.update(fields)
    return TimeBlock(user_id=user.id, **values)


def count_blocks(db_session, **filters) -> int:
    query = select(func.count()).select_from(TimeBlock)
    for column, value in filters.items():
        query = query.where(getattr(TimeBlock, column) == value)
    return db_session.execute(query).scalar_one()


def assert_database_rejects(db_session) -> None:
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_standalone_block_is_valid_and_gets_defaults(db_session):
    user = make_user(db_session)
    block = block_for(user)
    db_session.add(block)
    db_session.flush()

    assert block.id is not None
    assert block.status == "planned"
    assert block.task_id is None
    assert block.subject_id is None
    assert block.created_at is not None


def test_block_can_belong_to_a_task(db_session):
    user = make_user(db_session)
    task = make_task(db_session, user)
    block = block_for(user, task_id=task.id)
    db_session.add(block)
    db_session.flush()

    assert block.task_id == task.id


def test_block_can_belong_to_a_subject_without_a_task(db_session):
    user = make_user(db_session)
    subject = make_subject(db_session, user)
    block = block_for(user, subject_id=subject.id)
    db_session.add(block)
    db_session.flush()

    assert block.subject_id == subject.id


def test_task_can_have_several_blocks(db_session):
    user = make_user(db_session)
    task = make_task(db_session, user)
    db_session.add_all(
        [
            block_for(
                user,
                task_id=task.id,
                starts_at=START + timedelta(days=day),
                ends_at=END + timedelta(days=day),
            )
            for day in range(3)
        ]
    )
    db_session.flush()

    assert count_blocks(db_session, task_id=task.id) == 3


def test_database_allows_overlapping_blocks(db_session):
    """Overlaps are only a warning in the app, so the database must not forbid them."""
    user = make_user(db_session)
    db_session.add_all(
        [
            block_for(user, title="First"),
            block_for(user, title="Second", starts_at=START + timedelta(minutes=30)),
        ]
    )
    db_session.flush()

    assert count_blocks(db_session, user_id=user.id) == 2


def test_block_cannot_have_both_task_and_subject(db_session):
    user = make_user(db_session)
    task = make_task(db_session, user)
    subject = make_subject(db_session, user)
    db_session.add(block_for(user, task_id=task.id, subject_id=subject.id))

    assert_database_rejects(db_session)


@pytest.mark.parametrize("minutes", [0, -30])
def test_block_must_end_after_it_starts(db_session, minutes):
    user = make_user(db_session)
    db_session.add(block_for(user, ends_at=START + timedelta(minutes=minutes)))

    assert_database_rejects(db_session)


@pytest.mark.parametrize("status", ["done", "banana", ""])
def test_block_status_must_be_known(db_session, status):
    user = make_user(db_session)
    db_session.add(block_for(user, status=status))

    assert_database_rejects(db_session)


@pytest.mark.parametrize("status", ["planned", "completed", "skipped"])
def test_block_accepts_every_known_status(db_session, status):
    user = make_user(db_session)
    block = block_for(user, status=status)
    db_session.add(block)
    db_session.flush()

    assert block.status == status


def test_block_cannot_use_another_users_task(db_session):
    user = make_user(db_session)
    another_user = make_user(db_session)
    foreign_task = make_task(db_session, another_user)
    db_session.add(block_for(user, task_id=foreign_task.id))

    assert_database_rejects(db_session)


def test_block_cannot_use_another_users_subject(db_session):
    user = make_user(db_session)
    another_user = make_user(db_session)
    foreign_subject = make_subject(db_session, another_user)
    db_session.add(block_for(user, subject_id=foreign_subject.id))

    assert_database_rejects(db_session)


def test_deleting_a_task_deletes_only_its_blocks(db_session):
    user = make_user(db_session)
    task = make_task(db_session, user)
    other_task = make_task(db_session, user)
    db_session.add_all(
        [
            block_for(user, task_id=task.id),
            block_for(user, task_id=task.id),
            block_for(user, task_id=other_task.id),
            block_for(user),
        ]
    )
    db_session.flush()

    db_session.delete(task)
    db_session.flush()

    assert count_blocks(db_session, task_id=task.id) == 0
    assert count_blocks(db_session, user_id=user.id) == 2


def test_subject_with_blocks_cannot_be_deleted(db_session):
    user = make_user(db_session)
    subject = make_subject(db_session, user)
    db_session.add(block_for(user, subject_id=subject.id))
    db_session.flush()

    db_session.delete(subject)

    assert_database_rejects(db_session)

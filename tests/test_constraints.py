
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studyflow.models import Subject, Task, User


def test_task_cannot_reference_another_users_subject(
    db_session: Session,
) -> None:
    owner = User(email=f"owner-{uuid4()}@example.com")
    another_user = User(email=f"other-{uuid4()}@example.com")

    db_session.add_all([owner, another_user])
    db_session.flush()

    subject = Subject(name="Математика", user_id=owner.id)
    db_session.add(subject)
    db_session.flush()

    # Предмет принадлежит owner, а задача — другому пользователю.
    task = Task(
        user_id=another_user.id,
        subject_id=subject.id,
        title="Чужой предмет",
    )
    db_session.add(task)

    with pytest.raises(IntegrityError):
        db_session.flush()

    # После ошибки восстанавливаем состояние сессии.
    db_session.rollback()


def test_subject_with_tasks_cannot_be_deleted(
    db_session: Session,
) -> None:
    user = User(email=f"delete-test-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    subject = Subject(name="Математика", user_id=user.id)
    db_session.add(subject)
    db_session.flush()

    task = Task(
        user_id=user.id,
        subject_id=subject.id,
        title="Подготовить домашнее задание",
    )
    db_session.add(task)
    db_session.flush()

    db_session.delete(subject)

    # База должна запретить удаление предмета с задачей.
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()

from datetime import datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from studyflow.models.subject import Subject
from studyflow.models.task import Task
from studyflow.schemas.tasks import TaskCreate, TaskUpdate


class SubjectNotFoundError(Exception):
    """Raised when a subject does not exist or belongs to another user."""


def validate_subject(
    db: Session,
    user_id: UUID,
    subject_id: UUID | None,
) -> None:
    if subject_id is None:
        return

    subject = (
        db.query(Subject)
        .filter(
            Subject.id == subject_id,
            Subject.user_id == user_id,
        )
        .first()
    )

    if subject is None:
        raise SubjectNotFoundError("Subject not found")


def create_task(db: Session, user_id: UUID, data: TaskCreate) -> Task:
    validate_subject(
        db=db,
        user_id=user_id,
        subject_id=data.subject_id,
    )

    task = Task(
        user_id=user_id,
        title=data.title,
        description=data.description,
        subject_id=data.subject_id,
        deadline=data.deadline,
        status=data.status,
    )

    db.add(task)

    try:
        db.commit()
        db.refresh(task)
    except Exception:
        db.rollback()
        raise

    return task


def get_tasks(
    db: Session,
    user_id: UUID,
    status: Literal["todo", "in_progress", "completed"] | None = None,
    subject_id: UUID | None = None,
    date_filter: Literal["today", "overdue", "upcoming"] | None = None,
    timezone: str = "UTC",
    sort_by: Literal["created_at", "deadline"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> list[Task]:
    query = db.query(Task).filter(Task.user_id == user_id)

    if status is not None:
        query = query.filter(Task.status == status)

    if subject_id is not None:
        query = query.filter(Task.subject_id == subject_id)

    if date_filter == "today":
        user_timezone = ZoneInfo(timezone)
        today = datetime.now(user_timezone).date()

        start = datetime.combine(today, time.min, tzinfo=user_timezone)
        end = datetime.combine(
            today + timedelta(days=1),
            time.min,
            tzinfo=user_timezone,
        )

        query = query.filter(
            Task.deadline >= start,
            Task.deadline < end,
        )

    elif date_filter == "overdue":
        now = datetime.now(ZoneInfo(timezone))

        query = query.filter(
            Task.deadline < now,
            Task.status != "completed",
        )

    elif date_filter == "upcoming":
        now = datetime.now(ZoneInfo(timezone))

        query = query.filter(
            Task.deadline > now,
            Task.status != "completed",
        )

    sort_column = {
        "created_at": Task.created_at,
        "deadline": Task.deadline,
    }[sort_by]

    if order == "asc":
        ordering = sort_column.asc()
    else:
        ordering = sort_column.desc()

    if sort_by == "deadline":
        ordering = ordering.nullslast()

    return query.order_by(ordering).all()


def get_task(
    db: Session,
    user_id: UUID,
    task_id: UUID,
) -> Task | None:
    return (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.user_id == user_id,
        )
        .first()
    )


def update_task(
    db: Session,
    user_id: UUID,
    task_id: UUID,
    data: TaskUpdate,
) -> Task | None:
    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.user_id == user_id,
        )
        .first()
    )

    if task is None:
        return None

    if not data.model_fields_set:
        raise ValueError("No fields to update")

    updates = data.model_dump(exclude_unset=True)

    if "title" in updates and updates["title"] is None:
        raise ValueError("Title cannot be null")

    if "status" in updates and updates["status"] is None:
        raise ValueError("Status cannot be null")

    if updates.get("status") not in (
        None,
        "todo",
        "in_progress",
        "completed",
    ):
        raise ValueError("Invalid task status")

    if "subject_id" in updates:
        validate_subject(
            db=db,
            user_id=user_id,
            subject_id=updates["subject_id"],
        )

    for field, value in updates.items():
        setattr(task, field, value)

    try:
        db.commit()
        db.refresh(task)
    except Exception:
        db.rollback()
        raise

    return task


def delete_task(
    db: Session,
    user_id: UUID,
    task_id: UUID,
) -> bool:
    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.user_id == user_id,
        )
        .first()
    )

    if task is None:
        return False

    try:
        db.delete(task)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return True

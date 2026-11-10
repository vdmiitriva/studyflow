from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, aliased

from studyflow.models.task import Task
from studyflow.models.time_block import TimeBlock
from studyflow.schemas.time_blocks import BlockCreate, BlockUpdate
from studyflow.services.tasks import SubjectNotFoundError, validate_subject

MAX_PERIOD = timedelta(days=62)
MAX_CONFLICTS_SHOWN = 10

__all__ = [
    "BlockConflictError",
    "SubjectNotFoundError",
    "TaskNotFoundError",
    "create_block",
    "delete_block",
    "find_conflicts",
    "get_block",
    "get_conflict_ids",
    "get_conflict_map",
    "list_blocks",
    "update_block",
]


class TaskNotFoundError(Exception):
    """Raised when a task does not exist or belongs to another user."""


class BlockConflictError(Exception):
    """Raised when a block overlaps other planned blocks and the user has
    not confirmed that this is fine."""

    def __init__(self, conflicts: list[TimeBlock]) -> None:
        super().__init__("Time block overlaps with existing blocks")
        self.conflicts = conflicts


def overlaps(first_start: Any, first_end: Any, second_start: Any, second_end: Any):
    """Two periods overlap when each of them starts before the other one ends.

    Periods that only touch (one ends exactly when the other starts) do not
    overlap. The same rule is used to find the blocks of a calendar period and
    to find conflicts, so it is written only once.
    """
    return and_(first_start < second_end, first_end > second_start)


def get_task_of_user(db: Session, user_id: UUID, task_id: UUID) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))

    if task is None:
        raise TaskNotFoundError("Task not found")

    return task


def get_block(db: Session, user_id: UUID, block_id: UUID) -> TimeBlock | None:
    return db.scalar(
        select(TimeBlock).where(
            TimeBlock.id == block_id,
            TimeBlock.user_id == user_id,
        )
    )


def find_conflicts(
    db: Session,
    user_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    exclude_id: UUID | None = None,
) -> list[TimeBlock]:
    """Planned blocks of the user that overlap the given period."""
    query = select(TimeBlock).where(
        TimeBlock.user_id == user_id,
        TimeBlock.status == "planned",
        overlaps(TimeBlock.starts_at, TimeBlock.ends_at, starts_at, ends_at),
    )

    if exclude_id is not None:
        query = query.where(TimeBlock.id != exclude_id)

    query = query.order_by(TimeBlock.starts_at, TimeBlock.id)
    return list(db.scalars(query.limit(MAX_CONFLICTS_SHOWN)))


def get_conflict_ids(db: Session, block: TimeBlock) -> list[UUID]:
    if block.status != "planned":
        return []

    conflicts = find_conflicts(
        db,
        block.user_id,
        block.starts_at,
        block.ends_at,
        exclude_id=block.id,
    )
    return [conflict.id for conflict in conflicts]


def create_block(
    db: Session,
    user_id: UUID,
    data: BlockCreate,
    allow_conflicts: bool = False,
) -> TimeBlock:
    title = data.title

    if data.task_id is not None:
        task = get_task_of_user(db, user_id, data.task_id)
        title = title or task.title

    validate_subject(db, user_id, data.subject_id)

    if data.status == "planned" and not allow_conflicts:
        conflicts = find_conflicts(db, user_id, data.starts_at, data.ends_at)

        if conflicts:
            raise BlockConflictError(conflicts)

    block = TimeBlock(
        user_id=user_id,
        task_id=data.task_id,
        subject_id=data.subject_id,
        title=title,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        status=data.status,
    )
    db.add(block)

    try:
        db.commit()
        db.refresh(block)
    except Exception:
        db.rollback()
        raise

    return block


def update_block(
    db: Session,
    user_id: UUID,
    block_id: UUID,
    data: BlockUpdate,
    allow_conflicts: bool = False,
) -> TimeBlock | None:
    block = get_block(db, user_id, block_id)

    if block is None:
        return None

    changes = data.model_dump(exclude_unset=True)

    # What the block would look like after the update. The schema only sees
    # the request, so rules that involve the stored values are checked here.
    new_task_id = changes.get("task_id", block.task_id)
    new_subject_id = changes.get("subject_id", block.subject_id)
    new_start = changes.get("starts_at", block.starts_at)
    new_end = changes.get("ends_at", block.ends_at)
    new_status = changes.get("status", block.status)

    if new_end <= new_start:
        raise ValueError("Block must end after it starts")

    if new_task_id is not None and new_subject_id is not None:
        raise ValueError("A block cannot have both a task and a subject")

    if changes.get("task_id") is not None:
        get_task_of_user(db, user_id, changes["task_id"])

    if changes.get("subject_id") is not None:
        validate_subject(db, user_id, changes["subject_id"])

    # Renaming a block that is already in a conflict must not be blocked,
    # so conflicts are only checked when the time or the status changes.
    time_or_status_changed = bool({"starts_at", "ends_at", "status"} & changes.keys())

    if new_status == "planned" and time_or_status_changed and not allow_conflicts:
        conflicts = find_conflicts(
            db,
            user_id,
            new_start,
            new_end,
            exclude_id=block.id,
        )

        if conflicts:
            raise BlockConflictError(conflicts)

    for field, value in changes.items():
        setattr(block, field, value)

    try:
        db.commit()
        db.refresh(block)
    except Exception:
        db.rollback()
        raise

    return block


def delete_block(db: Session, user_id: UUID, block_id: UUID) -> bool:
    block = get_block(db, user_id, block_id)

    if block is None:
        return False

    try:
        db.delete(block)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return True


def list_blocks(
    db: Session,
    user_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> list[TimeBlock]:
    """Blocks that take place at any moment of [period_start, period_end).

    A block that began before the period but is still going on inside it
    belongs to the period too, so both ends of the block are compared.
    """
    if period_end <= period_start:
        raise ValueError("Period must end after it starts")

    if period_end - period_start > MAX_PERIOD:
        raise ValueError("Period cannot be longer than 62 days")

    query = (
        select(TimeBlock)
        .where(
            TimeBlock.user_id == user_id,
            overlaps(TimeBlock.starts_at, TimeBlock.ends_at, period_start, period_end),
        )
        .order_by(TimeBlock.starts_at, TimeBlock.id)
    )
    return list(db.scalars(query))


def get_conflict_map(
    db: Session,
    user_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> dict[UUID, list[UUID]]:
    """For every planned block of the period: ids of planned blocks it overlaps."""
    other = aliased(TimeBlock)

    query = (
        select(TimeBlock.id, other.id)
        .join(
            other,
            and_(
                other.user_id == TimeBlock.user_id,
                other.id != TimeBlock.id,
                other.status == "planned",
                overlaps(
                    TimeBlock.starts_at,
                    TimeBlock.ends_at,
                    other.starts_at,
                    other.ends_at,
                ),
            ),
        )
        .where(
            TimeBlock.user_id == user_id,
            TimeBlock.status == "planned",
            overlaps(TimeBlock.starts_at, TimeBlock.ends_at, period_start, period_end),
        )
        .order_by(TimeBlock.starts_at, other.starts_at, other.id)
    )

    conflicts: dict[UUID, list[UUID]] = {}

    for block_id, other_id in db.execute(query).all():
        conflicts.setdefault(block_id, []).append(other_id)

    return conflicts

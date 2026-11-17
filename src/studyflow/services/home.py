from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from studyflow.models.subject import Subject
from studyflow.models.task import Task
from studyflow.models.time_block import TimeBlock

BlockWithSubject = tuple[TimeBlock, Subject | None]


def select_blocks_with_subject(user_id: UUID) -> Select:
    """Blocks of the user together with the subject that gives them a color.

    A block has the subject it was given directly, or else the subject of its
    task. A block without either has no subject (None).
    """
    subject_id = func.coalesce(TimeBlock.subject_id, Task.subject_id)

    return (
        select(TimeBlock, Subject)
        .select_from(TimeBlock)
        .outerjoin(
            Task,
            and_(Task.id == TimeBlock.task_id, Task.user_id == TimeBlock.user_id),
        )
        .outerjoin(
            Subject,
            and_(Subject.id == subject_id, Subject.user_id == TimeBlock.user_id),
        )
        .where(TimeBlock.user_id == user_id)
    )


def get_current_blocks(
    db: Session,
    user_id: UUID,
    now: datetime,
) -> list[BlockWithSubject]:
    """Planned blocks that are going on at `now`.

    A block that starts exactly now is already going on, a block that ends
    exactly now is already over.
    """
    query = (
        select_blocks_with_subject(user_id)
        .where(
            TimeBlock.status == "planned",
            TimeBlock.starts_at <= now,
            TimeBlock.ends_at > now,
        )
        .order_by(TimeBlock.starts_at, TimeBlock.id)
    )
    return [(block, subject) for block, subject in db.execute(query)]


def get_next_block(
    db: Session,
    user_id: UUID,
    now: datetime,
) -> BlockWithSubject | None:
    """The planned block that starts soonest after `now`."""
    query = (
        select_blocks_with_subject(user_id)
        .where(TimeBlock.status == "planned", TimeBlock.starts_at > now)
        .order_by(TimeBlock.starts_at, TimeBlock.id)
        .limit(1)
    )
    row = db.execute(query).first()

    if row is None:
        return None

    return row[0], row[1]

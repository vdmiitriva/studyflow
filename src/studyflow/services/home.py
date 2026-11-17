from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from studyflow.models.subject import Subject
from studyflow.models.task import Task
from studyflow.models.time_block import TimeBlock

BlockWithSubject = tuple[TimeBlock, Subject | None]
TaskWithSubject = tuple[Task, Subject | None]

SUGGESTIONS_SHOWN = 3
DEADLINES_SHOWN = 5

# High priority first, then medium, then low.
PRIORITY_RANK = case(
    (Task.priority == "high", 0),
    (Task.priority == "medium", 1),
    else_=2,
)


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


def select_tasks_with_subject(user_id: UUID) -> Select:
    """Tasks of the user together with their subject (None without one)."""
    return (
        select(Task, Subject)
        .select_from(Task)
        .outerjoin(
            Subject,
            and_(Subject.id == Task.subject_id, Subject.user_id == Task.user_id),
        )
        .where(Task.user_id == user_id)
    )


def get_current_task(db: Session, user_id: UUID) -> TaskWithSubject | None:
    """The task the user is working on.

    With several tasks in progress the one with the nearest deadline wins, then
    the one created earlier. A task without a deadline comes last.
    """
    query = (
        select_tasks_with_subject(user_id)
        .where(Task.status == "in_progress")
        .order_by(Task.deadline.asc().nulls_last(), Task.created_at.asc(), Task.id)
        .limit(1)
    )
    row = db.execute(query).first()

    if row is None:
        return None

    return row[0], row[1]


def get_suggested_tasks(
    db: Session,
    user_id: UUID,
    exclude_task_id: UUID | None,
) -> list[TaskWithSubject]:
    """Unfinished tasks worth starting, other than the current task.

    Order: nearest deadline, then priority, then the shorter estimate. A task
    without a deadline (or without an estimate) comes after the others.
    """
    query = select_tasks_with_subject(user_id).where(Task.status != "completed")

    if exclude_task_id is not None:
        query = query.where(Task.id != exclude_task_id)

    query = query.order_by(
        Task.deadline.asc().nulls_last(),
        PRIORITY_RANK,
        Task.estimate_minutes.asc().nulls_last(),
        Task.created_at.asc(),
        Task.id,
    ).limit(SUGGESTIONS_SHOWN)

    return [(task, subject) for task, subject in db.execute(query)]


@dataclass
class Deadlines:
    overdue_total: int
    upcoming_total: int
    tasks: list[TaskWithSubject]


def get_deadlines(db: Session, user_id: UUID, now: datetime) -> Deadlines:
    """The nearest deadlines of unfinished tasks and how many there are in all.

    Ordering by the deadline puts the overdue ones first, the oldest of them
    at the very top, and then the future ones from the nearest to the farthest.
    The totals count every matching task, not only the ones in the list.
    """
    unfinished = (
        Task.user_id == user_id,
        Task.status != "completed",
        Task.deadline.is_not(None),
    )

    totals = db.execute(
        select(
            func.count(Task.id).filter(Task.deadline < now),
            func.count(Task.id).filter(Task.deadline >= now),
        ).where(*unfinished)
    ).one()

    query = (
        select_tasks_with_subject(user_id)
        .where(Task.status != "completed", Task.deadline.is_not(None))
        .order_by(Task.deadline, Task.created_at, Task.id)
        .limit(DEADLINES_SHOWN)
    )

    return Deadlines(
        overdue_total=totals[0],
        upcoming_total=totals[1],
        tasks=[(task, subject) for task, subject in db.execute(query)],
    )


def urgency_of(deadline: datetime | None, now: datetime, zone: ZoneInfo) -> str | None:
    """How urgent a deadline is, by the exact moment and the user's calendar.

    overdue: the moment has passed. today: still ahead, on today's date.
    soon: tomorrow, the day after tomorrow or the day after that. later: more.
    """
    if deadline is None:
        return None

    if deadline < now:
        return "overdue"

    today = now.astimezone(zone).date()
    day = deadline.astimezone(zone).date()

    if day == today:
        return "today"

    if day <= today + timedelta(days=3):
        return "soon"

    return "later"


def reason_of(
    priority: str,
    deadline: datetime | None,
    urgency: str | None,
) -> str | None:
    """Why a task is suggested, as a code the page turns into a sentence."""
    if urgency == "overdue":
        return "overdue"

    if urgency == "today":
        return "due_today"

    if urgency == "soon":
        return "due_soon"

    if priority == "high":
        return "high_priority"

    if deadline is None:
        return "no_deadline"

    return None

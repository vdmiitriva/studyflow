from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from studyflow.models.time_block import TimeBlock
from studyflow.schemas.series import (
    MAX_SERIES_BLOCKS,
    FollowingUpdate,
    SeriesCreate,
)
from studyflow.schemas.time_blocks import BlockSummary
from studyflow.services.tasks import validate_subject
from studyflow.services.time_blocks import (
    find_conflicts,
    get_block,
    get_task_of_user,
)

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass
class PlannedBlock:
    """A block that is about to be created and the blocks it would overlap."""

    block: TimeBlock
    conflicts: list[TimeBlock]


class SeriesConflictError(Exception):
    """Raised when blocks of a new series overlap existing planned blocks and
    the user has not confirmed that this is fine."""

    def __init__(self, conflicting: list[PlannedBlock]) -> None:
        super().__init__("Some blocks of the series overlap existing blocks")
        self.conflicting = conflicting


def series_dates(
    first_date: date,
    last_date: date,
    repeat: str,
    weekdays: list[str] | None,
) -> list[date]:
    """The days of a series, both the first and the last day included."""
    wanted = {WEEKDAYS[name] for name in weekdays or []}
    dates: list[date] = []

    for offset in range((last_date - first_date).days + 1):
        day = first_date + timedelta(days=offset)

        if repeat == "daily" or day.weekday() in wanted:
            dates.append(day)

    return dates


def to_instant(day: date, start_time: time, zone: ZoneInfo) -> datetime:
    """The moment when `start_time` happens on `day` on the user's wall clock.

    A time that does not exist (the clocks jump forward) moves forward by the
    length of the gap, and a time that happens twice (the clocks go back)
    means its first occurrence.
    """
    local = datetime.combine(day, start_time).replace(tzinfo=zone)
    return local.astimezone(UTC)


def plan_series(
    db: Session,
    user_id: UUID,
    timezone: str,
    data: SeriesCreate,
) -> list[PlannedBlock]:
    """Check the request and build every block, saving nothing."""
    title = data.title

    if data.task_id is not None:
        task = get_task_of_user(db, user_id, data.task_id)
        title = title or task.title

    validate_subject(db, user_id, data.subject_id)

    days = series_dates(data.first_date, data.last_date, data.repeat, data.weekdays)

    if not days:
        raise ValueError("The series has no blocks in this period")

    if len(days) > MAX_SERIES_BLOCKS:
        raise ValueError(f"A series cannot have more than {MAX_SERIES_BLOCKS} blocks")

    zone = ZoneInfo(timezone)
    duration = timedelta(minutes=data.duration_minutes)
    series_id = uuid4()
    planned: list[PlannedBlock] = []

    for day in days:
        starts_at = to_instant(day, data.start_time, zone)
        block = TimeBlock(
            user_id=user_id,
            series_id=series_id,
            task_id=data.task_id,
            subject_id=data.subject_id,
            title=title,
            starts_at=starts_at,
            ends_at=starts_at + duration,
            status="planned",
        )
        conflicts = find_conflicts(db, user_id, block.starts_at, block.ends_at)
        planned.append(PlannedBlock(block, conflicts))

    return planned


def create_series(
    db: Session,
    user_id: UUID,
    timezone: str,
    data: SeriesCreate,
    allow_conflicts: bool = False,
) -> list[TimeBlock]:
    """Create all blocks of a series in one transaction, or none of them."""
    planned = plan_series(db, user_id, timezone, data)
    conflicting = [item for item in planned if item.conflicts]

    if conflicting and not allow_conflicts:
        raise SeriesConflictError(conflicting)

    blocks = [item.block for item in planned]
    series_id = blocks[0].series_id
    db.add_all(blocks)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    query = (
        select(TimeBlock)
        .where(TimeBlock.user_id == user_id, TimeBlock.series_id == series_id)
        .order_by(TimeBlock.starts_at)
    )
    return list(db.scalars(query))


@dataclass
class ConflictingMove:
    """A changed block whose new time overlaps other planned blocks.

    Plain values are used on purpose: when the change is cancelled the
    database objects go back to their old state, but this data must survive.
    """

    title: str
    starts_at: datetime
    ends_at: datetime
    conflicts: list[BlockSummary]


class FollowingConflictError(Exception):
    """Raised when changed blocks overlap other planned blocks and the user
    has not confirmed that this is fine."""

    def __init__(self, conflicting: list[ConflictingMove]) -> None:
        super().__init__("Some changed blocks overlap other planned blocks")
        self.conflicting = conflicting


def get_series_block(db: Session, user_id: UUID, block_id: UUID) -> TimeBlock | None:
    block = get_block(db, user_id, block_id)

    if block is not None and block.series_id is None:
        raise ValueError("The block is not part of a series")

    return block


def following_blocks(db: Session, user_id: UUID, block: TimeBlock) -> list[TimeBlock]:
    """The block itself and the later planned blocks of its series.

    The chosen block only marks the starting point, so it may have any status.
    Earlier, completed and skipped blocks are never part of the operation.
    """
    query = (
        select(TimeBlock)
        .where(
            TimeBlock.user_id == user_id,
            TimeBlock.series_id == block.series_id,
            TimeBlock.status == "planned",
            TimeBlock.starts_at >= block.starts_at,
        )
        .order_by(TimeBlock.starts_at, TimeBlock.id)
    )
    return list(db.scalars(query))


def moved_times(
    block: TimeBlock,
    zone: ZoneInfo,
    start_time: time | None,
    duration_minutes: int | None,
) -> tuple[datetime, datetime]:
    """The new start and end of a block.

    The block stays on its own local date (in the user's current time zone).
    What is not given keeps its old value.
    """
    starts_at = block.starts_at

    if start_time is not None:
        starts_at = to_instant(starts_at.astimezone(zone).date(), start_time, zone)

    if duration_minutes is not None:
        ends_at = starts_at + timedelta(minutes=duration_minutes)
    else:
        ends_at = starts_at + (block.ends_at - block.starts_at)

    return starts_at, ends_at


def update_following(
    db: Session,
    user_id: UUID,
    timezone: str,
    block_id: UUID,
    data: FollowingUpdate,
    allow_conflicts: bool = False,
) -> list[TimeBlock] | None:
    """Change the time of a block and of the planned blocks after it.

    Everything happens in one transaction. The new times are first written
    inside a SAVEPOINT, so the database sees the new position of every block
    and conflicts can be found between the changed blocks too. If there are
    conflicts and the user has not confirmed them, only the SAVEPOINT is
    cancelled and nothing is changed.
    """
    block = get_series_block(db, user_id, block_id)

    if block is None:
        return None

    blocks = following_blocks(db, user_id, block)

    if not blocks:
        raise ValueError("There are no planned blocks to change")

    zone = ZoneInfo(timezone)
    new_times = [
        moved_times(item, zone, data.start_time, data.duration_minutes)
        for item in blocks
    ]
    block_ids = [item.id for item in blocks]

    try:
        savepoint = db.begin_nested()

        for item, (starts_at, ends_at) in zip(blocks, new_times, strict=True):
            item.starts_at = starts_at
            item.ends_at = ends_at

        db.flush()

        conflicting: list[ConflictingMove] = []

        for item in blocks:
            found = find_conflicts(
                db,
                user_id,
                item.starts_at,
                item.ends_at,
                exclude_id=item.id,
            )

            if found:
                conflicting.append(
                    ConflictingMove(
                        title=item.title,
                        starts_at=item.starts_at,
                        ends_at=item.ends_at,
                        conflicts=[BlockSummary.model_validate(c) for c in found],
                    )
                )

        if conflicting and not allow_conflicts:
            savepoint.rollback()
            # Make sure no object keeps the cancelled values in memory.
            db.expire_all()
            raise FollowingConflictError(conflicting)

        savepoint.commit()
        db.commit()
    except FollowingConflictError:
        raise
    except Exception:
        db.rollback()
        raise

    query = (
        select(TimeBlock)
        .where(TimeBlock.user_id == user_id, TimeBlock.id.in_(block_ids))
        .order_by(TimeBlock.starts_at)
    )
    return list(db.scalars(query))


def delete_following(db: Session, user_id: UUID, block_id: UUID) -> int | None:
    """Delete a block and the planned blocks after it, return how many."""
    block = get_series_block(db, user_id, block_id)

    if block is None:
        return None

    block_ids = [item.id for item in following_blocks(db, user_id, block)]

    try:
        db.execute(
            delete(TimeBlock).where(
                TimeBlock.user_id == user_id,
                TimeBlock.id.in_(block_ids),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return len(block_ids)

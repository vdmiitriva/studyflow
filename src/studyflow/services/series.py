from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from studyflow.models.time_block import TimeBlock
from studyflow.schemas.series import MAX_SERIES_BLOCKS, SeriesCreate
from studyflow.services.tasks import validate_subject
from studyflow.services.time_blocks import find_conflicts, get_task_of_user

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

from collections.abc import Iterable
from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from studyflow.models.time_block import TimeBlock
from studyflow.services.time_blocks import check_period, overlaps

Period = tuple[datetime, datetime]


def merge_periods(periods: Iterable[Period]) -> list[Period]:
    """Join periods that overlap or touch into longer ones."""
    merged: list[Period] = []

    for start, end in sorted(periods):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    return merged


def subtract_busy(window: Period, busy: list[Period]) -> list[Period]:
    """The parts of the window that no busy period covers.

    `busy` must be sorted and merged (see merge_periods).
    """
    start, end = window
    free: list[Period] = []
    cursor = start

    for busy_start, busy_end in busy:
        if busy_end <= cursor:
            continue

        if busy_start >= end:
            break

        if busy_start > cursor:
            free.append((cursor, busy_start))

        cursor = max(cursor, busy_end)

        if cursor >= end:
            break

    if cursor < end:
        free.append((cursor, end))

    return free


def work_windows(
    period_start: datetime,
    period_end: datetime,
    zone: ZoneInfo,
    day_start: time,
    day_end: time,
) -> list[Period]:
    """The working hours of every local day, cut to the requested period.

    Days are counted in the user's time zone, so 08:00 stays 08:00 on the
    wall clock even when the clocks change.
    """
    day = period_start.astimezone(zone).date()
    last_day = (period_end - timedelta(microseconds=1)).astimezone(zone).date()
    windows: list[Period] = []

    while day <= last_day:
        start = max(datetime.combine(day, day_start, tzinfo=zone), period_start)
        end = min(datetime.combine(day, day_end, tzinfo=zone), period_end)

        if start < end:
            windows.append((start, end))

        day += timedelta(days=1)

    return windows


def get_free_windows(
    db: Session,
    user_id: UUID,
    timezone: str,
    period_start: datetime,
    period_end: datetime,
    day_start: time,
    day_end: time,
    min_minutes: int,
) -> list[Period]:
    """Free time inside the working hours, between the planned blocks."""
    check_period(period_start, period_end)

    if day_end <= day_start:
        raise ValueError("Work day must end after it starts")

    zone = ZoneInfo(timezone)

    rows = db.execute(
        select(TimeBlock.starts_at, TimeBlock.ends_at)
        .where(
            TimeBlock.user_id == user_id,
            TimeBlock.status == "planned",
            overlaps(TimeBlock.starts_at, TimeBlock.ends_at, period_start, period_end),
        )
        .order_by(TimeBlock.starts_at)
    ).all()
    busy = merge_periods((start, end) for start, end in rows)

    shortest = timedelta(minutes=min_minutes)
    free: list[Period] = []

    for window in work_windows(period_start, period_end, zone, day_start, day_end):
        for start, end in subtract_busy(window, busy):
            if end - start >= shortest:
                free.append((start.astimezone(zone), end.astimezone(zone)))

    return free

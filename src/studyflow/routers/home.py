from dataclasses import asdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.clock import get_now
from studyflow.models.user import User
from studyflow.schemas.calendar import FreeWindow
from studyflow.schemas.home import (
    HomeBlock,
    HomeDeadlines,
    HomeResponse,
    HomeSubject,
    HomeTask,
    HomeWeek,
    SuggestedTask,
)
from studyflow.services import home as home_service
from studyflow.services.home import BlockWithSubject, TaskWithSubject

router = APIRouter(prefix="/home", tags=["Home"])


def to_home_block(item: BlockWithSubject, zone: ZoneInfo) -> HomeBlock:
    block, subject = item

    return HomeBlock(
        id=block.id,
        title=block.title,
        starts_at=block.starts_at.astimezone(zone),
        ends_at=block.ends_at.astimezone(zone),
        task_id=block.task_id,
        subject=HomeSubject.model_validate(subject) if subject is not None else None,
    )


def task_data(item: TaskWithSubject, now: datetime, zone: ZoneInfo) -> dict:
    task, subject = item

    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "deadline": task.deadline.astimezone(zone) if task.deadline else None,
        "urgency": home_service.urgency_of(task.deadline, now, zone),
        "estimate_minutes": task.estimate_minutes,
        "subject": HomeSubject.model_validate(subject) if subject else None,
    }


def to_home_task(item: TaskWithSubject, now: datetime, zone: ZoneInfo) -> HomeTask:
    return HomeTask(**task_data(item, now, zone))


def to_suggested_task(
    item: TaskWithSubject,
    now: datetime,
    zone: ZoneInfo,
) -> SuggestedTask:
    data = task_data(item, now, zone)
    task = item[0]
    reason = home_service.reason_of(task.priority, task.deadline, data["urgency"])

    return SuggestedTask(**data, reason=reason)


def to_free_window(start: datetime, end: datetime) -> FreeWindow:
    # The length is taken in UTC: two moments with the same time zone object
    # are subtracted by the wall clock, which ignores a clock change.
    elapsed = end.astimezone(UTC) - start.astimezone(UTC)

    return FreeWindow(
        starts_at=start,
        ends_at=end,
        minutes=int(elapsed.total_seconds() // 60),
    )


@router.get("", response_model=HomeResponse)
def read_home(
    now: datetime = Depends(get_now),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HomeResponse:
    zone = ZoneInfo(user.timezone)
    following = home_service.get_next_block(db, user.id, now)
    current_task = home_service.get_current_task(db, user.id)
    suggested = home_service.get_suggested_tasks(
        db,
        user.id,
        exclude_task_id=current_task[0].id if current_task else None,
    )
    deadlines = home_service.get_deadlines(db, user.id, now)
    week = home_service.get_week_stats(db, user.id, now, zone)
    free_today = home_service.get_free_today(
        db,
        user.id,
        user.timezone,
        user.day_start,
        user.day_end,
        now,
    )

    return HomeResponse(
        now=[
            to_home_block(item, zone)
            for item in home_service.get_current_blocks(db, user.id, now)
        ],
        next=to_home_block(following, zone) if following is not None else None,
        current_task=(
            to_home_task(current_task, now, zone) if current_task is not None else None
        ),
        suggested=[to_suggested_task(item, now, zone) for item in suggested],
        deadlines=HomeDeadlines(
            overdue_total=deadlines.overdue_total,
            upcoming_total=deadlines.upcoming_total,
            tasks=[to_home_task(item, now, zone) for item in deadlines.tasks],
        ),
        week=HomeWeek(**asdict(week)),
        free_today=[to_free_window(start, end) for start, end in free_today],
    )

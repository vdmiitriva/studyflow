import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from studyflow.schemas.tasks import TaskPriority, TaskStatus

Urgency = Literal["overdue", "today", "soon", "later"]
SuggestionReason = Literal[
    "overdue",
    "due_today",
    "due_soon",
    "high_priority",
    "no_deadline",
]


class HomeSubject(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str


class HomeBlock(BaseModel):
    id: uuid.UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    task_id: uuid.UUID | None
    subject: HomeSubject | None


class HomeTask(BaseModel):
    id: uuid.UUID
    title: str
    status: TaskStatus
    priority: TaskPriority
    deadline: datetime | None
    urgency: Urgency | None
    estimate_minutes: int | None
    subject: HomeSubject | None


class SuggestedTask(HomeTask):
    # None when there is no particular reason: a far deadline, normal priority.
    reason: SuggestionReason | None


class HomeDeadlines(BaseModel):
    overdue_total: int
    upcoming_total: int
    tasks: list[HomeTask]


class HomeResponse(BaseModel):
    now: list[HomeBlock]
    next: HomeBlock | None
    current_task: HomeTask | None
    suggested: list[SuggestedTask]
    deadlines: HomeDeadlines

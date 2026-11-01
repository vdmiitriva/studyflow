import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["todo", "in_progress", "completed"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    subject_id: uuid.UUID | None = None
    deadline: datetime | None = None
    status: TaskStatus = "todo"


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    subject_id: uuid.UUID | None
    title: str
    description: str | None
    deadline: datetime | None
    status: TaskStatus
    created_at: datetime


class TaskUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    description: str | None = None
    subject_id: uuid.UUID | None = None
    deadline: datetime | None = None
    status: TaskStatus | None = None

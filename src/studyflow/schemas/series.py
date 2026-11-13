import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from studyflow.schemas.common import HourMinute, IsoDate
from studyflow.schemas.time_blocks import BlockSummary, clean_title

MAX_SERIES_DAYS = 183
MAX_SERIES_BLOCKS = 200

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class SeriesCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    task_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    first_date: IsoDate
    last_date: IsoDate
    start_time: HourMinute
    duration_minutes: int = Field(ge=1, le=1440)
    repeat: Literal["daily", "weekly"]
    weekdays: list[Weekday] | None = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: str | None) -> str | None:
        return clean_title(value)

    @model_validator(mode="after")
    def check_series(self):
        if self.last_date < self.first_date:
            raise ValueError("A series cannot end before it starts")

        if (self.last_date - self.first_date).days + 1 > MAX_SERIES_DAYS:
            raise ValueError(f"A series cannot be longer than {MAX_SERIES_DAYS} days")

        if self.task_id is not None and self.subject_id is not None:
            raise ValueError("A block cannot have both a task and a subject")

        if self.title is None and self.task_id is None:
            raise ValueError("A block without a task needs a title")

        if self.repeat == "daily" and self.weekdays is not None:
            raise ValueError("Weekdays are only used for weekly series")

        if self.repeat == "weekly" and not self.weekdays:
            raise ValueError("A weekly series needs at least one weekday")

        return self


class SeriesPreviewBlock(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    conflicts: list[BlockSummary]


class SeriesPreviewResponse(BaseModel):
    total_blocks: int
    conflicting_blocks: int
    blocks: list[SeriesPreviewBlock]


class SeriesConflictResponse(BaseModel):
    message: str
    total_conflicting_blocks: int
    blocks: list[SeriesPreviewBlock]

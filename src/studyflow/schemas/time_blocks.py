import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

BlockStatus = Literal["planned", "completed", "skipped"]


def clean_title(value: str | None) -> str | None:
    if value is None:
        return value

    value = value.strip()

    if not value:
        raise ValueError("Title cannot be blank")

    return value


class BlockCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    task_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    status: BlockStatus = "planned"

    @field_validator("title")
    @classmethod
    def check_title(cls, value: str | None) -> str | None:
        return clean_title(value)

    @model_validator(mode="after")
    def check_block(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Block must end after it starts")

        if self.task_id is not None and self.subject_id is not None:
            raise ValueError("A block cannot have both a task and a subject")

        if self.title is None and self.task_id is None:
            raise ValueError("A block without a task needs a title")

        return self


class BlockUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    task_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    status: BlockStatus | None = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: str | None) -> str | None:
        return clean_title(value)

    @model_validator(mode="after")
    def check_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        # task_id and subject_id may be null (that detaches the block),
        # the other fields must always have a value.
        for field in ("title", "starts_at", "ends_at", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("Block must end after it starts")

        if self.task_id is not None and self.subject_id is not None:
            raise ValueError("A block cannot have both a task and a subject")

        return self


class BlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID | None
    subject_id: uuid.UUID | None
    title: str
    starts_at: datetime
    ends_at: datetime
    status: BlockStatus
    created_at: datetime
    conflicting_block_ids: list[uuid.UUID] = Field(default_factory=list)


class BlockSummary(BaseModel):
    """A short description of a block, used in conflict warnings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    starts_at: datetime
    ends_at: datetime


class BlockConflictResponse(BaseModel):
    message: str
    conflicts: list[BlockSummary]

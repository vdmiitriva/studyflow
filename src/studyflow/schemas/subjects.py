import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studyflow.models.subject import DEFAULT_SUBJECT_COLOR

COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    color: str = Field(default=DEFAULT_SUBJECT_COLOR, pattern=COLOR_PATTERN)


class SubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str = Field(min_length=1, max_length=150)
    color: str
    status: str
    created_at: datetime


class SubjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)

    @model_validator(mode="after")
    def check_name_provided(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self

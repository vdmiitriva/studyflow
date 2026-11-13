from datetime import time

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from studyflow.schemas.common import HourMinute
from studyflow.timezones import is_valid_timezone


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr | None
    name: str | None
    timezone: str
    day_start: time
    day_end: time

    @field_serializer("day_start", "day_end")
    def format_day_limit(self, value: time) -> str:
        return value.strftime("%H:%M")


class UserUpdate(BaseModel):
    timezone: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    day_start: HourMinute | None = None
    day_end: HourMinute | None = None

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_timezone(value):
            raise ValueError("Unknown time zone")
        return value

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.strip()

        if not value:
            raise ValueError("Name cannot be blank")

        return value

    @model_validator(mode="after")
    def check_provided_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        if (
            self.day_start is not None
            and self.day_end is not None
            and self.day_start >= self.day_end
        ):
            raise ValueError("Day must end after it starts")

        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

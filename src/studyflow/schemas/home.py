import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class HomeResponse(BaseModel):
    now: list[HomeBlock]
    next: HomeBlock | None

from datetime import datetime

from pydantic import BaseModel


class FreeWindow(BaseModel):
    starts_at: datetime
    ends_at: datetime
    minutes: int

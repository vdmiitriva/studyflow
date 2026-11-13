import re
from datetime import time
from typing import Annotated

from pydantic import BeforeValidator

_HOUR_MINUTE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def require_hour_minute(value: object) -> object:
    """Only text like 08:00 is accepted: no seconds, no time zone, no numbers."""
    if not isinstance(value, str) or _HOUR_MINUTE.fullmatch(value) is None:
        raise ValueError("Time must look like HH:MM, for example 08:00")

    return value


HourMinute = Annotated[time, BeforeValidator(require_hour_minute)]

import re
from datetime import date, time
from typing import Annotated

from pydantic import BeforeValidator

_HOUR_MINUTE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def require_hour_minute(value: object) -> object:
    """Only text like 08:00 is accepted: no seconds, no time zone, no numbers."""
    if not isinstance(value, str) or _HOUR_MINUTE.fullmatch(value) is None:
        raise ValueError("Time must look like HH:MM, for example 08:00")

    return value


HourMinute = Annotated[time, BeforeValidator(require_hour_minute)]


def require_iso_date(value: object) -> object:
    """Only text like 2026-11-10 is accepted, not numbers or other formats."""
    if not isinstance(value, str) or _ISO_DATE.fullmatch(value) is None:
        raise ValueError("Date must look like YYYY-MM-DD, for example 2026-11-10")

    return value


IsoDate = Annotated[date, BeforeValidator(require_iso_date)]

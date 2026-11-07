from functools import lru_cache
from zoneinfo import available_timezones


@lru_cache(maxsize=1)
def known_timezones() -> frozenset[str]:
    """All IANA time zone names, for example "Europe/Moscow" or "UTC"."""
    return frozenset(available_timezones())


def is_valid_timezone(name: str) -> bool:
    return name in known_timezones()

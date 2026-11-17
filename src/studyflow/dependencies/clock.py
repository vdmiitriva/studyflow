from datetime import UTC, datetime


def get_now() -> datetime:
    """The current moment. Tests replace it to pretend it is another time."""
    return datetime.now(UTC)

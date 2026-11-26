"""Time helpers: every timestamp in Nestor is timezone-aware UTC; days of the week are named in the household's
clock."""

from datetime import UTC, date, datetime
from enum import StrEnum


class Day(StrEnum):
    """A day of the week, Monday first."""

    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"

    @classmethod
    def of(cls, day: date) -> "Day":
        return tuple(cls)[day.weekday()]


def utc_now() -> datetime:
    return datetime.now(UTC)

"""A wake-up: an instruction the agent runs at a time, once or on chosen days, in the household's clock."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address


class Day(StrEnum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


DAYS = tuple(Day)  # Monday first, as `datetime.weekday()` counts


@dataclass(frozen=True, slots=True, kw_only=True)
class Schedule:
    """`at` for once; else `times` on `days` (every day when empty), in the household's time zone."""

    id: str
    instruction: str  # what the agent does when it wakes: "send Mathis the morning news on Telegram"
    owner: PersonId | None = None  # on whose behalf it runs
    created_in: Address | None = None
    at: datetime | None = None  # aware
    times: tuple[time, ...] = ()
    days: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (self.at is None) == (not self.times):
            raise ContractError("a schedule runs either once (`at`) or at `times`, not both nor neither")
        if unknown := set(self.days) - set(DAYS):
            raise ContractError(f"unknown days {', '.join(sorted(unknown))}: use {', '.join(DAYS)}")

    @property
    def recurring(self) -> bool:
        return self.at is None

    def next_due(self, after: datetime, timezone: str) -> datetime | None:
        """The first time it is due strictly after `after` (aware), or `None` once a one-off has passed."""
        if self.at is not None:
            return self.at if self.at > after else None
        zone = ZoneInfo(timezone)
        local = after.astimezone(zone)
        for offset in range(8):
            day = local.date() + timedelta(days=offset)
            if self.days and DAYS[day.weekday()] not in self.days:
                continue
            for moment in sorted(self.times):
                due = datetime.combine(day, moment, tzinfo=zone)
                if due > after:
                    return due
        return None

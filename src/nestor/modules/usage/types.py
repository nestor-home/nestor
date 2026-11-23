"""Values of usage: who consumes, why, how a cost was found, and what is asked of the ledger."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from nestor.core import ModelType, Money, PersonId, SessionId, Unit
from nestor.modules.channels import Medium


class CallPurpose(StrEnum):
    """Why Nestor called: what the call serves, whichever model type answers it."""

    TURN = "turn"  # answering a person, whatever it takes (transcribing their voice, a picture they asked for)
    NOTIFICATION = "notification"  # telling someone of a task, a reminder, a watch, a message
    TITLE = "title"  # naming a conversation
    WATCH = "watch"  # sorting what came in for the watches
    CONSOLIDATION = "consolidation"  # summing up a conversation that ended into memory
    INDEXING = "indexing"  # embedding memories and episodes to find them by meaning
    ENROLLMENT = "enrollment"  # recording a person's voice
    TASK = "task"  # work delegated to an executor, and what it asks of Nestor meanwhile
    SEARCH = "search"  # a person searching the memories from the admin
    UNATTRIBUTED = "unattributed"  # a call nobody said the reason of: a fault to fix, shown as such


class CostBasis(StrEnum):
    """How a cost is known."""

    REPORTED = "reported"  # the provider said what it billed
    PRICED = "priced"  # units times a price: the configuration's, or the public catalogue's
    FREE = "free"  # a model of the household's own, or a price of zero
    NOTHING = "nothing"  # nothing consumed nor billed: a call that failed before it was sent
    UNKNOWN = "unknown"  # neither said nor priced: never counted as zero


class Outcome(StrEnum):
    OK = "ok"
    FAILED = "failed"  # the provider refused or failed: what it billed before still counts
    CANCELLED = "cancelled"  # cut short (barge-in, a stopped answer)


# How a price is written for each unit, as providers publish them: tokens and characters per million, speech per
# minute, a picture or a request apiece.
PRICED_PER: Mapping[Unit, int] = {
    Unit.INPUT_TOKENS: 1_000_000,
    Unit.CACHED_INPUT_TOKENS: 1_000_000,
    Unit.CACHE_WRITE_TOKENS: 1_000_000,
    Unit.OUTPUT_TOKENS: 1_000_000,
    Unit.CHARACTERS: 1_000_000,
    Unit.AUDIO_SECONDS: 60,
    Unit.IMAGES: 1,
    Unit.REQUESTS: 1,
}
ZERO = Money(0)


_INPUT_PARTS = (Unit.CACHED_INPUT_TOKENS, Unit.CACHE_WRITE_TOKENS)  # counted in the input, priced apart when they can


@dataclass(frozen=True, slots=True)
class Rates:
    """A price: dollars for one of each unit, and where it comes from (`config`, `catalogue:2026-11-23`). A unit it
    has no rate for is not billed by it; the parts of the input read from or written to the cache are billed as
    input unless it prices them apart."""

    per_unit: Mapping[Unit, Decimal]
    source: str

    @classmethod
    def written(cls, prices: Mapping[Unit, float | Decimal], source: str) -> "Rates":
        """From prices as people write them (`PRICED_PER`: dollars per million tokens, per minute…)."""
        return cls({u: Decimal(str(p)) / PRICED_PER[u] for u, p in prices.items()}, source)

    def cost(self, units: Mapping[Unit, float]) -> Money | None:
        """What `units` cost, or `None` when it prices none of them."""
        billed = {u: Decimal(str(q)) for u, q in units.items() if q}
        if Unit.INPUT_TOKENS in billed:
            for part in _INPUT_PARTS:
                if part in billed and part in self.per_unit:
                    billed[Unit.INPUT_TOKENS] -= billed[part]
            billed[Unit.INPUT_TOKENS] = max(billed[Unit.INPUT_TOKENS], Decimal(0))
        for part in _INPUT_PARTS:
            if part not in self.per_unit:
                billed.pop(part, None)
        priced = [q * self.per_unit[u] for u, q in billed.items() if u in self.per_unit]
        return Money.usd(sum(priced, Decimal(0))) if priced else None


@dataclass(frozen=True, slots=True)
class Priced:
    cost: Money | None  # none when unknown
    basis: CostBasis
    source: str | None = None  # where the price came from, for a cost `priced`: `config`, `catalogue:<date>`


@dataclass(frozen=True, slots=True, kw_only=True)
class Consumer:
    """A model of `models` or an executor, as the ledger names and prices it."""

    key: str  # its name in the configuration
    kind: ModelType
    provider: str  # who bills it: the provider's brand when known (`openrouter`), else its plugin (`anthropic`)
    model: str | None = None  # the model the configuration asks for, to price it when the provider names none
    local: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class Attribution:
    """On whose behalf and why a call is made, set where the work starts (`attributed`) and read by the meter."""

    purpose: CallPurpose = CallPurpose.UNATTRIBUTED
    person: PersonId | None = None
    channel: str | None = None
    medium: Medium | None = None
    session: SessionId | None = None  # the address the work belongs to
    conversation: str | None = None
    turn: str | None = None
    origin: str | None = None  # what the work comes from: `watch:<id>`, `schedule:<id>`, `task:<id>`


class Dimension(StrEnum):
    """What spending is grouped or filtered by: the ledger's columns, shared by the API and the admin."""

    CONSUMER = "consumer"  # the model of `models`, or the executor
    KIND = "kind"
    PROVIDER = "provider"
    SERVED = "served"  # the model that answered, as its provider names it
    PURPOSE = "purpose"
    PERSON = "person"
    CHANNEL = "channel"
    MEDIUM = "medium"
    BASIS = "basis"
    OUTCOME = "outcome"
    ORIGIN = "origin"
    CONVERSATION = "conversation"


class Period(StrEnum):
    """The spans spending is read over, in the household's days: today, the last 7, 30 or 90 days (today included),
    or the calendar month so far."""

    TODAY = "today"
    WEEK = "7d"
    THIRTY_DAYS = "30d"
    MONTH = "month"
    QUARTER = "90d"


class Interval(StrEnum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True, slots=True, kw_only=True)
class UsageFilter:
    """Which calls: those at or after `since` and before `until`, whose value of each dimension is one of those
    given. `None` for a value matches calls without one (no person: Nestor's own work)."""

    since: datetime | None = None
    until: datetime | None = None
    only: Mapping[Dimension, frozenset[str | None]] = field(default_factory=dict)


BUCKETS: Mapping[Period, Interval] = {
    Period.TODAY: Interval.HOUR,
    Period.WEEK: Interval.DAY,
    Period.THIRTY_DAYS: Interval.DAY,
    Period.MONTH: Interval.DAY,
    Period.QUARTER: Interval.WEEK,
}


@dataclass(frozen=True, slots=True)
class Span:
    """A period resolved in the household's clock: from `since` to `until`."""

    period: Period
    since: datetime
    until: datetime

    @property
    def every(self) -> Interval:
        """The buckets the period is drawn in."""
        return BUCKETS[self.period]

    def keeping(self, only: Mapping[Dimension, frozenset[str | None]]) -> UsageFilter:
        return UsageFilter(since=self.since, until=self.until, only=only)


@dataclass(frozen=True, slots=True)
class Totals:
    """What a set of calls cost and consumed."""

    cost: Money = ZERO  # what is known: reported, priced or free
    calls: int = 0
    unknown: int = 0  # calls of unknown cost, left out of `cost`
    units: Mapping[Unit, float] = field(default_factory=dict)
    duration_ms: int = 0
    conversations: int = 0  # the conversations the calls served
    conversed: Money = ZERO  # what the calls made in a conversation cost (not the background work)


@dataclass(frozen=True, slots=True)
class Group:
    key: str | None  # the dimension's value; `None` for calls without one
    totals: Totals


@dataclass(frozen=True, slots=True)
class Point:
    start: datetime  # the bucket's start, in the household's time zone
    groups: tuple[Group, ...]


@dataclass(frozen=True, slots=True)
class Beat:
    """What was spent at one hour of one weekday (0 for Monday), over a period: when the household spends."""

    weekday: int
    hour: int
    cost: Money
    calls: int

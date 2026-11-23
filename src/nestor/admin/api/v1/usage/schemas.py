"""Spending as the admin shows it: amounts in nano-dollars (the front formats them), units by name, people named."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import People, PersonRef
from nestor.core import ModelType, PersonId, Unit
from nestor.modules.channels import Medium
from nestor.modules.usage import (
    PRICED_PER,
    Beat,
    CallPurpose,
    Consumer,
    CostBasis,
    Dimension,
    Group,
    Interval,
    Line,
    Outcome,
    Period,
    Point,
    Rates,
    Span,
    Summary,
    Totals,
)

Values = list[str] | None  # the values kept of a dimension; an empty one keeps the calls without one


class UsageQuery(BaseModel):
    """What every reading takes: a period of the household's clock, and for each dimension the values to keep
    (repeated; an empty value keeps the calls without one, such as Nestor's own work for `person`)."""

    period: Period = Period.THIRTY_DAYS
    consumer: Values = None
    kind: Values = None
    provider: Values = None
    served: Values = None
    purpose: Values = None
    person: Values = None
    channel: Values = None
    medium: Values = None
    basis: Values = None
    outcome: Values = None
    origin: Values = None
    conversation: Values = None

    def kept(self) -> dict[Dimension, frozenset[str | None]]:
        """The values kept, by dimension (each field but the period is one, of its name)."""
        asked = {Dimension(name): getattr(self, name) for name in type(self).model_fields if name != "period"}
        return {d: frozenset(v or None for v in values) for d, values in asked.items() if values}


class SpanOut(BaseModel):
    period: Period
    since: datetime
    until: datetime
    every: Interval  # the buckets the period is drawn in

    @classmethod
    def of(cls, span: Span) -> "SpanOut":
        return cls(period=span.period, since=span.since, until=span.until, every=span.every)


class TotalsOut(BaseModel):
    cost_nusd: int  # what is known: billed, estimated or free
    calls: int
    unknown: int  # calls of unknown cost, left out of `cost_nusd`
    units: dict[Unit, float]
    duration_ms: int
    conversations: int
    conversed_nusd: int  # what the calls made in a conversation cost (not the background work)

    @classmethod
    def of(cls, totals: Totals) -> "TotalsOut":
        return cls(
            cost_nusd=totals.cost.nusd,
            calls=totals.calls,
            unknown=totals.unknown,
            units=dict(totals.units),
            duration_ms=totals.duration_ms,
            conversations=totals.conversations,
            conversed_nusd=totals.conversed.nusd,
        )


class SummaryOut(BaseModel):
    span: SpanOut
    totals: TotalsOut
    previous: TotalsOut  # the period of the same length just before
    month: TotalsOut  # this calendar month so far
    projected_month_nusd: int  # the month's spending if it goes on as so far

    @classmethod
    def of(cls, summary: Summary) -> "SummaryOut":
        return cls(
            span=SpanOut.of(summary.span),
            totals=TotalsOut.of(summary.totals),
            previous=TotalsOut.of(summary.previous),
            month=TotalsOut.of(summary.month),
            projected_month_nusd=summary.projected_month.nusd,
        )


class GroupOut(BaseModel):
    key: str | None  # the dimension's value; none for calls without one (Nestor's own work, for a person)
    person: PersonRef | None = None  # who `key` is, grouped by person
    totals: TotalsOut

    @classmethod
    def of(cls, group: Group, by: Dimension | None, people: People) -> "GroupOut":
        person = people.ref(PersonId(group.key)) if by is Dimension.PERSON and group.key else None
        return cls(key=group.key, person=person, totals=TotalsOut.of(group.totals))


class GroupsOut(BaseModel):
    by: Dimension
    groups: list[GroupOut]


class PointOut(BaseModel):
    start: datetime
    groups: list[GroupOut]


class SeriesOut(BaseModel):
    span: SpanOut
    by: Dimension | None
    points: list[PointOut]

    @classmethod
    def of(cls, span: Span, points: list[Point], by: Dimension | None, people: People) -> "SeriesOut":
        return cls(
            span=SpanOut.of(span),
            by=by,
            points=[PointOut(start=p.start, groups=[GroupOut.of(g, by, people) for g in p.groups]) for p in points],
        )


class BeatOut(BaseModel):
    weekday: int  # 0 for Monday
    hour: int
    cost_nusd: int
    calls: int

    @classmethod
    def of(cls, beat: Beat) -> "BeatOut":
        return cls(weekday=beat.weekday, hour=beat.hour, cost_nusd=beat.cost.nusd, calls=beat.calls)


class RhythmOut(BaseModel):
    beats: list[BeatOut]  # the hours of the week calls were made at


class CallOut(BaseModel):
    """One call: what it consumed, what it cost and how that is known, on whose behalf and why."""

    id: str
    position: int  # in the journal
    at: datetime
    consumer: str
    kind: ModelType
    provider: str
    served: str | None
    units: dict[Unit, float]
    cost_nusd: int | None
    basis: CostBasis
    price: str | None
    duration_ms: int
    outcome: Outcome
    purpose: CallPurpose
    person: PersonRef | None
    channel: str | None
    medium: Medium | None
    session: str | None
    conversation: str | None
    turn: str | None
    origin: str | None

    @classmethod
    def of(cls, line: Line, people: People) -> "CallOut":
        call = line.call
        return cls(
            **{f: getattr(call, f) for f in cls.model_fields if f not in ("position", "person", "units")},
            position=line.position,
            person=people.ref(call.person),
            units=dict(call.units),
        )


class CallsOut(BaseModel):
    calls: list[CallOut]
    next_before: int | None  # the cursor of the next page; none at the first call


class PriceOut(BaseModel):
    """How a model's calls are valued when its provider does not say what it billed."""

    consumer: str
    kind: ModelType
    provider: str
    model: str | None
    local: bool  # the household's own: free
    source: str | None  # `config`, `catalogue:<date>`; none: the provider's bill, else unknown
    prices: dict[Unit, float]  # as written (`PRICED_PER`): per million tokens or characters, per minute, apiece

    @classmethod
    def of(cls, consumer: Consumer, rates: Rates | None) -> "PriceOut":
        return cls(
            consumer=consumer.key,
            kind=consumer.kind,
            provider=consumer.provider,
            model=consumer.model,
            local=consumer.local,
            source=rates.source if rates is not None else None,
            prices={u: float(r * PRICED_PER[u]) for u, r in rates.per_unit.items()} if rates is not None else {},
        )


class PricesOut(BaseModel):
    catalogue: bool  # whether the public price list is read
    prices: list[PriceOut]

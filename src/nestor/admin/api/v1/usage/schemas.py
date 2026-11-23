"""Spending as the admin shows it: amounts in nano-dollars (the front formats them), units by name, people named."""

from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import People, PersonRef
from nestor.core import PersonId, Unit
from nestor.modules.channels import Medium
from nestor.modules.usage import (
    PRICED_PER,
    CallPurpose,
    Consumer,
    ConsumerKind,
    CostBasis,
    Dimension,
    Group,
    Line,
    Outcome,
    Point,
    Rates,
    Summary,
    Totals,
)


class TotalsOut(BaseModel):
    cost_nusd: int  # what is known: billed, estimated or free
    calls: int
    unknown: int  # calls of unknown cost, left out of `cost_nusd`
    units: dict[Unit, float]
    duration_ms: int

    @classmethod
    def of(cls, totals: Totals) -> "TotalsOut":
        return cls(
            cost_nusd=totals.cost.nusd,
            calls=totals.calls,
            unknown=totals.unknown,
            units=dict(totals.units),
            duration_ms=totals.duration_ms,
        )


class SummaryOut(BaseModel):
    since: datetime
    until: datetime
    totals: TotalsOut
    previous: TotalsOut  # the period of the same length just before
    month: TotalsOut  # this calendar month so far
    projected_month_nusd: int  # the month's spending if it goes on as so far
    conversations: int  # conversations the period's calls served

    @classmethod
    def of(cls, summary: Summary, since: datetime, until: datetime) -> "SummaryOut":
        return cls(
            since=since,
            until=until,
            totals=TotalsOut.of(summary.totals),
            previous=TotalsOut.of(summary.previous),
            month=TotalsOut.of(summary.month),
            projected_month_nusd=summary.projected_month.nusd,
            conversations=summary.conversations,
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
    every: str
    by: Dimension | None
    timezone: str
    points: list[PointOut]

    @classmethod
    def of(cls, points: list[Point], every: str, by: Dimension | None, timezone: str, people: People) -> "SeriesOut":
        return cls(
            every=every,
            by=by,
            timezone=timezone,
            points=[PointOut(start=p.start, groups=[GroupOut.of(g, by, people) for g in p.groups]) for p in points],
        )


class CallOut(BaseModel):
    """One call: what it consumed, what it cost and how that is known, on whose behalf and why."""

    id: str
    position: int  # in the journal
    at: datetime
    consumer: str
    kind: ConsumerKind
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
        return cls(
            id=line.id,
            position=line.position,
            at=line.at,
            consumer=line.consumer,
            kind=line.kind,
            provider=line.provider,
            served=line.served,
            units=dict(line.units),
            cost_nusd=line.cost.nusd if line.cost is not None else None,
            basis=line.basis,
            price=line.price,
            duration_ms=line.duration_ms,
            outcome=line.outcome,
            purpose=line.purpose,
            person=people.ref(line.person),
            channel=line.channel,
            medium=line.medium,
            session=line.session,
            conversation=line.conversation,
            turn=line.turn,
            origin=line.origin,
        )


class CallsOut(BaseModel):
    calls: list[CallOut]
    before: int | None  # where the next page starts; none at the first call


class PriceOut(BaseModel):
    """How a model's calls are valued when its provider does not say what it billed."""

    consumer: str
    kind: ConsumerKind
    provider: str
    model: str | None
    local: bool  # the household's own: free
    source: str | None  # `config`, `catalogue:<date>`; none: unknown
    prices: dict[Unit, float]  # as written: dollars per million tokens or characters, per minute heard, apiece

    @classmethod
    def of(cls, consumer: Consumer, rates: Rates | None) -> "PriceOut":
        written: Mapping[Unit, float] = (
            {u: float(r * PRICED_PER[u]) for u, r in rates.per_unit.items()} if rates is not None else {}
        )
        return cls(
            consumer=consumer.key,
            kind=consumer.kind,
            provider=consumer.provider,
            model=consumer.model,
            local=consumer.local,
            source=rates.source if rates is not None else None,
            prices=dict(written),
        )


class PricesOut(BaseModel):
    catalogue: bool  # whether the public price list is read
    prices: list[PriceOut]

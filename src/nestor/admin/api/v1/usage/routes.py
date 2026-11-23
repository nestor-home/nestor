"""Spending: what Nestor's calls to models and executors cost, on whose behalf, why, with which models, when.

`usage.read.all` reads every call; `usage.read.own` only those made for the account's person. Every reading takes
the same filters: a period (`since`, `until`; the last 30 days by default) and, for each dimension, the values to
keep (repeated; an empty value keeps the calls without one, such as Nestor's own work for `person`).
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.api.v1.usage.schemas import (
    CallOut,
    CallsOut,
    GroupOut,
    GroupsOut,
    PriceOut,
    PricesOut,
    SeriesOut,
    SummaryOut,
)
from nestor.admin.state import state
from nestor.core import utc_now
from nestor.modules.accounts import Scope
from nestor.modules.usage import Dimension, Interval, UsageFilter

router = APIRouter(tags=["usage"])
Reader = Annotated[Caller, Depends(allowed(Scope.USAGE_READ_ALL, Scope.USAGE_READ_OWN))]
DEFAULT_DAYS = 30
Values = Annotated[list[str] | None, Query()]


def _filters(
    caller: Reader,
    since: datetime | None = None,
    until: datetime | None = None,
    consumer: Values = None,
    kind: Values = None,
    provider: Values = None,
    served: Values = None,
    purpose: Values = None,
    person: Values = None,
    channel: Values = None,
    medium: Values = None,
    basis: Values = None,
    outcome: Values = None,
    origin: Values = None,
    conversation: Values = None,
) -> UsageFilter:
    """The calls asked for, within what the caller may read."""
    given = {
        Dimension.CONSUMER: consumer,
        Dimension.KIND: kind,
        Dimension.PROVIDER: provider,
        Dimension.SERVED: served,
        Dimension.PURPOSE: purpose,
        Dimension.PERSON: person,
        Dimension.CHANNEL: channel,
        Dimension.MEDIUM: medium,
        Dimension.BASIS: basis,
        Dimension.OUTCOME: outcome,
        Dimension.ORIGIN: origin,
        Dimension.CONVERSATION: conversation,
    }
    only = {d: frozenset(v or None for v in values) for d, values in given.items() if values}
    if not caller.principal.can(Scope.USAGE_READ_ALL):  # one's own requests, whatever else is asked
        own: frozenset[str | None] = frozenset({caller.person}) if caller.person else frozenset()
        only[Dimension.PERSON] = only[Dimension.PERSON] & own if Dimension.PERSON in only else own
    until = until or utc_now()
    return UsageFilter(since=since or until - timedelta(days=DEFAULT_DAYS), until=until, only=only)


Filtered = Annotated[UsageFilter, Depends(_filters)]


@router.get("/usage/summary")
async def usage_summary(request: Request, where: Filtered) -> SummaryOut:
    """The period at a glance: its spending, the period before, this month so far and where it is heading."""
    summary = await state(request).nestor.ledger.summary(where)
    assert where.since is not None and where.until is not None  # set by the filters
    return SummaryOut.of(summary, where.since, where.until)


@router.get("/usage/series")
async def usage_series(
    request: Request, where: Filtered, every: Interval = Interval.DAY, by: Dimension | None = None
) -> SeriesOut:
    """Spending over time, by hour, day, week or month of the household's clock, split by `by` if given."""
    nestor = state(request).nestor
    points = await nestor.ledger.series(where, every, by)
    return SeriesOut.of(points, every.value, by, nestor.ledger.timezone, People(nestor.household))


@router.get("/usage/groups")
async def usage_groups(
    request: Request, where: Filtered, by: Dimension, limit: Annotated[int | None, Query(ge=1, le=500)] = None
) -> GroupsOut:
    """Spending by value of a dimension, the costliest first."""
    nestor = state(request).nestor
    groups = await nestor.ledger.groups(where, by, limit=limit)
    people = People(nestor.household)
    return GroupsOut(by=by, groups=[GroupOut.of(g, by, people) for g in groups])


@router.get("/usage/calls")
async def usage_calls(
    request: Request,
    where: Filtered,
    before: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CallsOut:
    """The calls one by one, newest first; `before` (a journal position) pages back."""
    nestor = state(request).nestor
    lines = await nestor.ledger.lines(where, before=before, limit=limit)
    people = People(nestor.household)
    more = len(lines) == limit
    return CallsOut(calls=[CallOut.of(line, people) for line in lines], before=lines[-1].position if more else None)


@router.get("/usage/prices")
async def usage_prices(request: Request, caller: Reader) -> PricesOut:
    """How each model's calls are valued when its provider does not say what it billed, and where from."""
    nestor = state(request).nestor
    book = nestor.meter.prices
    return PricesOut(
        catalogue=nestor.price_catalogue is not None,
        prices=[PriceOut.of(c, None if c.local else book.rates(c)) for c in nestor.consumers],
    )

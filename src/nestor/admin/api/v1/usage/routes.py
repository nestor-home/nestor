"""Spending: what Nestor's calls to models cost, on whose behalf, why, with which models, when.

`usage.read.all` reads every call; `usage.read.own` only those made for the account's person. Every reading takes the
same query (`UsageQuery`): a period of the household's clock, and the values to keep of each dimension.
"""

from typing import Annotated, NamedTuple

from fastapi import APIRouter, Depends, Query, Request

from nestor.admin.api.v1.access import usage_reach
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.api.v1.usage.schemas import (
    BeatOut,
    CallOut,
    CallsOut,
    GroupOut,
    GroupsOut,
    PriceOut,
    PricesOut,
    RhythmOut,
    SeriesOut,
    SummaryOut,
    UsageQuery,
)
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.usage import Dimension, Span, UsageFilter

router = APIRouter(tags=["usage"])
Reader = Annotated[Caller, Depends(allowed(Scope.USAGE_READ_ALL, Scope.USAGE_READ_OWN))]


class Asked(NamedTuple):
    span: Span
    only: dict[Dimension, frozenset[str | None]]

    @property
    def where(self) -> UsageFilter:
        return self.span.keeping(self.only)


def _asked(
    request: Request,
    caller: Reader,
    query: Annotated[UsageQuery, Query()],
) -> Asked:
    """The period resolved in the household's clock, and the values kept, within what the caller may read."""
    return Asked(state(request).nestor.ledger.span(query.period), usage_reach(caller, query.kept()))


Read = Annotated[Asked, Depends(_asked)]


@router.get("/usage/summary")
async def usage_summary(request: Request, asked: Read) -> SummaryOut:
    """The period at a glance: its spending, the period before, this month so far and where it is heading."""
    return SummaryOut.of(await state(request).nestor.ledger.summary(asked.span, asked.only))


@router.get("/usage/series")
async def usage_series(request: Request, asked: Read, by: Dimension | None = None) -> SeriesOut:
    """Spending over the period, bucket by bucket (by hour today, by week over 90 days), split by `by` if given."""
    nestor = state(request).nestor
    points = await nestor.ledger.series(asked.where, asked.span.every, by)
    return SeriesOut.of(asked.span, points, by, People(nestor.household))


@router.get("/usage/groups")
async def usage_groups(request: Request, asked: Read, by: Dimension) -> GroupsOut:
    """Spending by value of a dimension, the costliest first."""
    nestor = state(request).nestor
    people = People(nestor.household)
    return GroupsOut(by=by, groups=[GroupOut.of(g, by, people) for g in await nestor.ledger.groups(asked.where, by)])


@router.get("/usage/rhythm")
async def usage_rhythm(request: Request, asked: Read) -> RhythmOut:
    """When the period's spending happened: by hour of each weekday."""
    return RhythmOut(beats=[BeatOut.of(b) for b in await state(request).nestor.ledger.rhythm(asked.where)])


@router.get("/usage/calls")
async def usage_calls(
    request: Request, asked: Read, before: int | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> CallsOut:
    """The calls one by one, newest first; `before` (a journal position) pages back."""
    nestor = state(request).nestor
    lines = await nestor.ledger.lines(asked.where, before=before, limit=limit)
    people = People(nestor.household)
    next_before = lines[-1].position if len(lines) == limit else None
    return CallsOut(calls=[CallOut.of(line, people) for line in lines], next_before=next_before)


@router.get("/usage/prices")
async def usage_prices(request: Request, caller: Reader) -> PricesOut:
    """How each model's calls are valued when its provider does not say what it billed, and where from."""
    nestor = state(request).nestor
    book = nestor.meter.prices
    return PricesOut(catalogue=book.catalogue, prices=[PriceOut.of(c, book.rates(c)) for c in nestor.consumers])

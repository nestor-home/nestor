"""The journal: pages of what happened, its filters, and a live stream of new entries (Server-Sent Events)."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.feed import Audience, Feed, Filters
from nestor.admin.api.v1.models import AgentActivityOut, JournalItem, People
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import CATEGORIES, OTHER_KEY
from nestor.admin.state import AdminState, state
from nestor.core import PersonId, utc_now
from nestor.modules.accounts import Scope

router = APIRouter(tags=["journal"])
Reader = Annotated[Caller, Depends(allowed(Scope.JOURNAL_READ_ALL, Scope.JOURNAL_READ_OWN))]
KINDS = frozenset(c.key for c in CATEGORIES) | {OTHER_KEY}
BUCKETS_S = (60, 300, 900, 1800, 3600, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 7 * 86400, 30 * 86400)
MAX_BUCKETS = 60


class JournalPage(BaseModel):
    items: list[JournalItem]  # newest first
    next_before: int | None  # pass it as `before` for the next (older) page; None at the beginning


class FacetOut(BaseModel):
    key: str
    label: str
    count: int  # entries kept by every other filter: a facet ignores its own selection


class HistogramOut(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    bucket_s: int
    counts: list[int]  # entries kept by every filter, per bucket from `from`


class JournalFacets(BaseModel):
    total: int  # entries kept by every filter
    truncated: bool  # counted over the newest entries in range only (see the API documentation)
    kinds: list[FacetOut]
    people: list[FacetOut]
    channels: list[FacetOut]
    rooms: list[FacetOut]
    histogram: HistogramOut


class JournalEntryOut(BaseModel):
    item: JournalItem
    record: dict[str, Any]  # the raw logged record: type, version, id, at, source, session, payload


def journal_filters(
    kinds: Annotated[str, Query(description="kind keys, comma-separated")] = "",
    person: str = "",
    channel: str = "",
    room: str = "",
    q: Annotated[str, Query(description="words in the rendered text or the raw content")] = "",
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    tone: Annotated[Literal["", "normal", "decision", "warning"], Query()] = "",
    session: str = "",
    task: str = "",
    watch: str = "",
    connection: str = "",
    satellite: str = "",
) -> Filters:
    chosen = frozenset(k.strip() for k in kinds.split(",") if k.strip())
    if unknown := chosen - KINDS:
        raise ApiError(400, "unknown_kind", kind=", ".join(sorted(unknown)))
    return Filters(
        kinds=chosen,
        person=person,
        channel=channel,
        room=room,
        q=q.strip(),
        since=from_,
        until=to,
        tone=tone,
        session=session,
        task=task,
        watch=watch,
        connection=connection,
        satellite=satellite,
    )


Chosen = Annotated[Filters, Depends(journal_filters)]


async def _feed(request: Request, caller: Caller, filters: Filters) -> Feed:
    admin = state(request)
    audience = await Audience.of(caller.principal, admin.nestor.journal.log)
    return Feed(admin, audience, filters, caller.phrasebook)


@router.get("/journal")
async def list_journal(
    request: Request,
    caller: Reader,
    filters: Chosen,
    before: Annotated[int | None, Query(ge=1, description="a position: entries strictly before it")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JournalPage:
    """Newest first. `kinds` are keys of the facets; `person` a person id; `channel` a channel name; `from`
    and `to` bound the time (`to` excluded); `session`, `task`, `watch`, `connection` and `satellite` keep
    one thread."""
    feed = await _feed(request, caller, filters)
    items, cursor = await feed.page(before=before, limit=limit)
    return JournalPage(items=items, next_before=cursor)


@router.get("/journal/facets")
async def get_journal_facets(request: Request, caller: Reader, filters: Chosen) -> JournalFacets:
    """Counts for the same filters, over the newest 10 000 entries of the range."""
    feed = await _feed(request, caller, filters)
    facets = await feed.facets()
    words, people = caller.phrasebook, People(state(request).nestor.household)
    return JournalFacets(
        total=facets.total,
        truncated=facets.truncated,
        kinds=[FacetOut(key=k, label=words.kind(k), count=n) for k, n in facets.kinds.most_common()],
        people=[
            FacetOut(key=k, label=ref.name if (ref := people.ref(PersonId(k))) else k, count=n)
            for k, n in facets.people.most_common()
        ],
        channels=[FacetOut(key=k, label=k, count=n) for k, n in facets.channels.most_common()],
        rooms=[FacetOut(key=k, label=k, count=n) for k, n in facets.rooms.most_common()],
        histogram=_histogram(facets.moments, filters),
    )


def _histogram(moments: list[datetime], filters: Filters) -> HistogramOut:
    start = filters.since or (min(moments) if moments else utc_now())
    end = filters.until or (max(moments) if moments else start)
    span = max(1.0, (end - start).total_seconds())
    bucket = next((b for b in BUCKETS_S if span / b <= MAX_BUCKETS), BUCKETS_S[-1])
    counts = [0] * (int(span // bucket) + 1)
    for moment in moments:
        index = int((moment - start).total_seconds() // bucket)
        if 0 <= index < len(counts):
            counts[index] += 1
    return HistogramOut(from_=start, to=end, bucket_s=bucket, counts=counts)


@router.get(
    "/journal/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Server-Sent Events: `event: item`, `id: <position>`, `data: <JournalItem as JSON>` (the schema "
                "`JournalItem`); comment lines as heartbeats. Same filters as the list. Resumes after "
                "`Last-Event-ID` (or `after`), else starts with new entries. With `agent.read`, also "
                "`event: activity`, `data: <AgentActivityOut as JSON>` (no `id`, the filters do not apply): "
                "once at the start, then on every change of what the agent is doing."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def stream_journal(
    request: Request,
    caller: Reader,
    filters: Chosen,
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    admin = state(request)
    feed = await _feed(request, caller, filters)
    resume = last_event_id if last_event_id and last_event_id.isdigit() else None
    start = int(resume) if resume else after if after is not None else await feed.last_position()
    return StreamingResponse(
        _events(admin, caller, feed, start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _events(admin: AdminState, caller: Caller, feed: Feed, position: int) -> AsyncIterator[str]:
    """New entries as they are written, and the agent's activity as it changes, until the client leaves,
    its session ends or the server stops. The journal subscription only wakes the loop: entries are read
    from the log, so none is missed."""
    subscription = admin.nestor.journal.subscribe()
    closing = asyncio.ensure_future(admin.closing.wait())
    monitor = admin.nestor.activity if caller.principal.can(Scope.AGENT_READ) else None
    sent: AgentActivityOut | None = None
    waits: set[asyncio.Future[Any]] = set()
    try:
        yield "retry: 3000\n\n"
        while True:
            changed = asyncio.ensure_future(monitor.changes().wait()) if monitor else None  # before reading it
            if monitor is not None and (activity := AgentActivityOut.of(monitor.current())) != sent:
                sent = activity
                yield f"event: activity\ndata: {json.dumps(activity.model_dump(mode='json'))}\n\n"
            items, position, more = await feed.after(position)
            for item in items:
                yield f"id: {item.position}\nevent: item\ndata: {json.dumps(item.model_dump(mode='json'))}\n\n"
            if more or (not _still_signed_in(admin, caller) or closing.done()):
                if changed:
                    changed.cancel()
                if more:
                    continue
                return
            woken = asyncio.ensure_future(subscription.next())
            waits = {woken, closing} | ({changed} if changed else set())
            done, _ = await asyncio.wait(waits, timeout=admin.settings.heartbeat_s, return_when=asyncio.FIRST_COMPLETED)
            for pending in waits - {closing} - done:
                pending.cancel()
            if not done:
                yield ": heartbeat\n\n"
    finally:
        for pending in waits:
            pending.cancel()
        closing.cancel()
        subscription.close()


@router.get("/journal/{position}")
async def get_journal_entry(request: Request, caller: Reader, position: int) -> JournalEntryOut:
    """One entry, with its raw record; 404 when it does not exist or is out of reach."""
    feed = await _feed(request, caller, Filters())
    found = await feed.get(position)
    if found is None:
        raise not_found("journal_entry_unknown")
    item, entry = found
    return JournalEntryOut(item=item, record=dict(entry.record))


def _still_signed_in(admin: AdminState, caller: Caller) -> bool:
    if caller.session is None or not admin.sessions.alive(caller.session):
        return False
    account = admin.accounts.accounts.get(caller.session.account_id or "")
    return account is not None and not account.disabled

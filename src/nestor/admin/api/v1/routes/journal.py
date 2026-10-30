"""The journal: pages of what happened, its filters, and a live stream of new entries (Server-Sent Events)."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.feed import Audience, Feed, Filters
from nestor.admin.api.v1.models import JournalItem, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import CATEGORIES
from nestor.admin.state import AdminState, state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["journal"])
Reader = Annotated[Caller, Depends(allowed(Scope.JOURNAL_READ_ALL, Scope.JOURNAL_READ_OWN))]


class JournalPage(BaseModel):
    items: list[JournalItem]  # newest first
    next_before: int | None  # pass it as `before` for the next (older) page; None at the beginning


class KindOut(BaseModel):
    key: str
    label: str


class ChannelOut(BaseModel):
    id: str  # the configured channel name, as journal items list it
    brand: str | None


class JournalFilters(BaseModel):
    kinds: list[KindOut]
    people: list[PersonRef]
    channels: list[ChannelOut]


def _filters(kind: str, person: str, channel: str) -> Filters:
    if kind and kind not in {c.key for c in CATEGORIES}:
        raise ApiError(400, "unknown_kind", kind=kind)
    return Filters(category=kind, person=person, channel=channel)


@router.get("/journal")
async def list_journal(
    request: Request,
    caller: Reader,
    kind: str = "",
    person: str = "",
    channel: str = "",
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JournalPage:
    """`kind` is a key of `GET /journal/filters` kinds; `person` a person id; `channel` a channel name."""
    admin = state(request)
    audience = await Audience.of(caller.principal, admin.nestor.journal.log)
    feed = Feed(admin, audience, _filters(kind, person, channel), caller.phrasebook)
    items, cursor = await feed.page(before=before, limit=limit)
    return JournalPage(items=items, next_before=cursor)


@router.get("/journal/filters")
async def get_journal_filters(request: Request, caller: Reader) -> JournalFilters:
    nestor = state(request).nestor
    return JournalFilters(
        kinds=[KindOut(key=c.key, label=caller.phrasebook.kind(c.key)) for c in CATEGORIES],
        people=[PersonRef(id=p.id, name=p.name) for p in nestor.household.people],
        channels=[
            ChannelOut(id=c.channel_id, brand=c.brand) for c in sorted(nestor.channels, key=lambda c: c.channel_id)
        ],
    )


@router.get(
    "/journal/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Server-Sent Events: `event: journal`, `id: <position>`, `data: <JournalItem as JSON>` (the schema "
                "`JournalItem`); comment "
                "lines as heartbeats. Resumes after `Last-Event-ID` (or `after`), else starts with new entries."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def stream_journal(
    request: Request,
    caller: Reader,
    kind: str = "",
    person: str = "",
    channel: str = "",
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    admin = state(request)
    filters = _filters(kind, person, channel)
    audience = await Audience.of(caller.principal, admin.nestor.journal.log)
    feed = Feed(admin, audience, filters, caller.phrasebook)
    resume = last_event_id if last_event_id and last_event_id.isdigit() else None
    start = int(resume) if resume else after if after is not None else await feed.last_position()
    return StreamingResponse(
        _events(admin, caller, feed, start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _events(admin: AdminState, caller: Caller, feed: Feed, position: int) -> AsyncIterator[str]:
    """New entries as they are written, until the client leaves, its session ends or the server stops.
    The journal subscription only wakes the loop: entries are read from the log, so none is missed."""
    subscription = admin.nestor.journal.subscribe()
    closing = asyncio.ensure_future(admin.closing.wait())
    try:
        yield "retry: 3000\n\n"
        while True:
            items, position, more = await feed.after(position)
            for item in items:
                yield f"id: {item.position}\nevent: journal\ndata: {json.dumps(item.model_dump(mode='json'))}\n\n"
            if more:
                continue
            if not _still_signed_in(admin, caller) or closing.done():
                return
            woken = asyncio.ensure_future(subscription.next())
            done, _ = await asyncio.wait(
                {woken, closing}, timeout=admin.settings.heartbeat_s, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                woken.cancel()
                yield ": heartbeat\n\n"
            elif woken not in done:
                woken.cancel()
    finally:
        closing.cancel()
        subscription.close()


def _still_signed_in(admin: AdminState, caller: Caller) -> bool:
    if caller.session is None or not admin.sessions.alive(caller.session):
        return False
    account = admin.accounts.accounts.get(caller.session.account_id or "")
    return account is not None and not account.disabled

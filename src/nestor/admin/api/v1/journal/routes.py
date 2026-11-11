"""The journal: pages of what happened, its filters, and a live stream of new entries (Server-Sent Events)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response, StreamingResponse

from nestor.admin.api.v1.errors import not_found
from nestor.admin.api.v1.journal.feed import Feed, Filters
from nestor.admin.api.v1.journal.schemas import (
    FacetOut,
    HistogramOut,
    JournalEntryOut,
    JournalFacets,
    JournalPage,
    KindFacetOut,
)
from nestor.admin.api.v1.journal.stream import events
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.presentation import Kind, Tone
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.accounts import Scope

router = APIRouter(tags=["journal"])
Reader = Annotated[Caller, Depends(allowed(Scope.JOURNAL_READ_ALL, Scope.JOURNAL_READ_OWN))]


def journal_filters(
    kinds: Annotated[tuple[Kind, ...], Query(description="keep these kinds; none: every kind")] = (),
    person: str = "",
    channel: str = "",
    room: str = "",
    q: Annotated[str, Query(description="words in the rendered text or the raw content")] = "",
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    tone: Tone | None = None,
    session: str = "",
    conversation: str = "",
    task: str = "",
    watch: str = "",
    connection: str = "",
    satellite: str = "",
) -> Filters:
    return Filters(
        kinds=frozenset(kinds),
        person=person,
        channel=channel,
        room=room,
        q=q.strip(),
        since=from_,
        until=to,
        tone=tone,
        session=session,
        conversation=conversation,
        task=task,
        watch=watch,
        connection=connection,
        satellite=satellite,
    )


Chosen = Annotated[Filters, Depends(journal_filters)]


@router.get("/journal")
async def list_journal(
    request: Request,
    caller: Reader,
    filters: Chosen,
    before: Annotated[int | None, Query(ge=1, description="a position: entries strictly before it")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JournalPage:
    """Newest first. `kinds` are keys of the facets; `person` a person id; `channel` a channel name; `from`
    and `to` bound the time (`to` excluded); `session`, `conversation`, `task`, `watch`, `connection` and
    `satellite` keep one thread."""
    feed = await Feed.of(state(request), caller.principal, filters, caller.phrasebook)
    items, cursor = await feed.page(before=before, limit=limit)
    return JournalPage(items=items, next_before=cursor)


@router.get("/journal/facets")
async def get_journal_facets(request: Request, caller: Reader, filters: Chosen) -> JournalFacets:
    """Counts for the same filters, over the newest 10 000 entries of the range."""
    admin = state(request)
    facets = await (await Feed.of(admin, caller.principal, filters, caller.phrasebook)).facets()
    people = People(admin.nestor.household)
    return JournalFacets(
        total=facets.total,
        truncated=facets.truncated,
        kinds=[KindFacetOut(key=k, count=n) for k, n in facets.kinds.most_common()],
        people=[
            FacetOut(key=k, label=ref.name if (ref := people.ref(PersonId(k))) else k, count=n)
            for k, n in facets.people.most_common()
        ],
        channels=[FacetOut(key=k, label=k, count=n) for k, n in facets.channels.most_common()],
        rooms=[FacetOut(key=k, label=k, count=n) for k, n in facets.rooms.most_common()],
        histogram=HistogramOut.of(facets.moments, filters.since, filters.until),
    )


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
    feed = await Feed.of(admin, caller.principal, filters, caller.phrasebook)
    resume = last_event_id if last_event_id and last_event_id.isdigit() else None
    start = int(resume) if resume else after if after is not None else await feed.last_position()
    return StreamingResponse(
        events(admin, caller, feed, start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/journal/{position}")
async def get_journal_entry(request: Request, caller: Reader, position: int) -> JournalEntryOut:
    """One entry, with its raw record; 404 when it does not exist or is out of reach."""
    feed = await Feed.of(state(request), caller.principal, Filters(), caller.phrasebook)
    found = await feed.get(position)
    if found is None:
        raise not_found("journal_entry_unknown")
    item, entry = found
    return JournalEntryOut(item=item, record=dict(entry.record))


SHOWN = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})  # what a browser may display inline


@router.get(
    "/journal/{position}/attachments/{index}",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "The file, as it was sent"}},
)
async def get_journal_attachment(request: Request, caller: Reader, position: int, index: int) -> Response:
    """A file sent with a message, to whoever reads the entry; 404 when either is out of reach. Pictures and
    recordings open in place; anything else is downloaded, so that a file sent to Nestor never runs in the admin."""
    admin = state(request)
    feed = await Feed.of(admin, caller.principal, Filters(), caller.phrasebook)
    found = await feed.get(position)
    attachments = feed.describer.describe(found[1]).attachments if found else ()
    if not 0 <= index < len(attachments):
        raise not_found("attachment_unknown")
    attached = attachments[index]
    try:
        data = await admin.nestor.blobs.get(attached.blob.digest)
    except KeyError:
        raise not_found("attachment_unknown") from None
    media_type = attached.blob.media_type
    inline = media_type in SHOWN or media_type.startswith("audio/")
    name = attached.name or f"{attached.kind.value}-{index}"
    headers = {
        "Cache-Control": "private, max-age=86400, immutable",  # addressed by content: it never changes
        "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{_ascii(name)}"',
        "Content-Security-Policy": "sandbox",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(data, media_type=media_type if inline else "application/octet-stream", headers=headers)


def _ascii(name: str) -> str:
    """A file name safe in a header."""
    return "".join(c if c.isascii() and c.isprintable() and c not in '"\\' else "_" for c in name)

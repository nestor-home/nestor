"""Active watches: what the assistant watches for, for whom, until when — and cancelling one.

`watches.manage.all` reaches every watch; `watches.manage.own` those kept for the account's person.
"""

from collections import Counter
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from nestor.admin.api.v1.errors import not_found
from nestor.admin.api.v1.models import People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import AdminState, state
from nestor.modules.accounts import Scope
from nestor.modules.initiative import Watch, WatchTriggered

router = APIRouter(tags=["watches"])
Manager = Annotated[Caller, Depends(allowed(Scope.WATCHES_MANAGE_ALL, Scope.WATCHES_MANAGE_OWN))]


class OriginOut(BaseModel):
    session: str  # the conversation it was asked in
    channel: str


class WatchOut(BaseModel):
    id: str
    what: str  # in the person's words
    keywords: list[str]
    kinds: list[str]  # what it watches ("mail")
    owner: PersonRef | None
    once: bool  # ends at the first match
    created_at: datetime
    until: datetime | None
    origin: OriginOut | None  # None when it was not asked in a conversation
    triggered: int  # how many items matched it so far
    last_triggered_at: datetime | None


class WatchesOut(BaseModel):
    watches: list[WatchOut]  # newest first
    kinds: list[str]  # what the plugged sources can bring; empty: no watch can trigger


def _reaches(caller: Caller, watch: Watch) -> bool:
    return caller.principal.reaches(watch.owner, every=Scope.WATCHES_MANAGE_ALL, own=Scope.WATCHES_MANAGE_OWN)


async def _triggers(admin: AdminState) -> tuple[Counter[str], dict[str, datetime]]:
    triggers: Counter[str] = Counter()
    last: dict[str, datetime] = {}
    for event in await admin.nestor.journal.history(WatchTriggered):
        triggers[event.watch_id] += 1
        last[event.watch_id] = event.at
    return triggers, last


def _watch(w: Watch, people: People, triggers: Counter[str], last: dict[str, datetime]) -> WatchOut:
    return WatchOut(
        id=w.id,
        what=w.what,
        keywords=list(w.keywords),
        kinds=list(w.kinds),
        owner=people.ref(w.owner),
        once=w.once,
        created_at=w.created_at,
        until=w.until,
        origin=OriginOut(session=str(w.created_in), channel=w.created_in.channel) if w.created_in else None,
        triggered=triggers[w.id],
        last_triggered_at=last.get(w.id),
    )


@router.get("/watches")
async def list_watches(request: Request, caller: Manager) -> WatchesOut:
    admin = state(request)
    people = People(admin.nestor.household)
    book = admin.nestor.watch_book
    watches = sorted(book.watches.values(), key=lambda w: w.created_at, reverse=True)
    triggers, last = await _triggers(admin)
    return WatchesOut(
        watches=[_watch(w, people, triggers, last) for w in watches if _reaches(caller, w)],
        kinds=sorted(book.kinds),
    )


@router.get("/watches/{watch_id}")
async def get_watch(request: Request, caller: Manager, watch_id: str) -> WatchOut:
    """One active watch; 404 when unknown, ended or out of reach."""
    admin = state(request)
    watch = admin.nestor.watch_book.watches.get(watch_id)
    if watch is None or not _reaches(caller, watch):
        raise not_found("watch_unknown")
    triggers, last = await _triggers(admin)
    return _watch(watch, People(admin.nestor.household), triggers, last)


@router.post("/watches/{watch_id}/cancel", status_code=204)
async def cancel_watch(request: Request, caller: Manager, watch_id: str) -> Response:
    book = state(request).nestor.watch_book
    watch = book.watches.get(watch_id)
    if watch is None or not _reaches(caller, watch):
        raise not_found("watch_unknown")
    await book.end(watch_id, "cancelled")
    return Response(status_code=204)

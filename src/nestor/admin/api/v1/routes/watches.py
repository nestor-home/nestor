"""Active watches: what the assistant watches for, for whom, until when — and cancelling one.

`watches.manage.all` reaches every watch; `watches.manage.own` those kept for the account's person.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from nestor.admin.api.v1.errors import not_found
from nestor.admin.api.v1.models import People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.initiative import Watch

router = APIRouter(tags=["watches"])
Manager = Annotated[Caller, Depends(allowed(Scope.WATCHES_MANAGE_ALL, Scope.WATCHES_MANAGE_OWN))]


class WatchOut(BaseModel):
    id: str
    what: str  # in the person's words
    keywords: list[str]
    kinds: list[str]  # what it watches ("mail")
    owner: PersonRef | None
    once: bool  # ends at the first match
    created_at: datetime
    until: datetime | None


class WatchesOut(BaseModel):
    watches: list[WatchOut]  # newest first
    kinds: list[str]  # what the plugged sources can bring; empty: no watch can trigger


def _reaches(caller: Caller, watch: Watch) -> bool:
    return caller.principal.reaches(watch.owner, every=Scope.WATCHES_MANAGE_ALL, own=Scope.WATCHES_MANAGE_OWN)


@router.get("/watches")
async def list_watches(request: Request, caller: Manager) -> WatchesOut:
    nestor = state(request).nestor
    people = People(nestor.household)
    book = nestor.watch_book
    watches = sorted(book.watches.values(), key=lambda w: w.created_at, reverse=True)
    return WatchesOut(
        watches=[
            WatchOut(
                id=w.id,
                what=w.what,
                keywords=list(w.keywords),
                kinds=list(w.kinds),
                owner=people.ref(w.owner),
                once=w.once,
                created_at=w.created_at,
                until=w.until,
            )
            for w in watches
            if _reaches(caller, w)
        ],
        kinds=sorted(book.kinds),
    )


@router.post("/watches/{watch_id}/cancel", status_code=204)
async def cancel_watch(request: Request, caller: Manager, watch_id: str) -> Response:
    book = state(request).nestor.watch_book
    watch = book.watches.get(watch_id)
    if watch is None or not _reaches(caller, watch):
        raise not_found("Cette veille n'existe pas ou est déjà terminée.")
    await book.end(watch_id, "cancelled")
    return Response(status_code=204)

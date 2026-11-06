"""Active watches: what the assistant watches for, for whom, until when — and cancelling one.

`watches.manage.all` reaches every watch; `watches.manage.own` those kept for the account's person.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.access import reachable_watch, reaches_watch
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.api.v1.watches.schemas import WatchesOut, WatchOut
from nestor.admin.api.v1.watches.triggers import Triggers
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["watches"])
Manager = Annotated[Caller, Depends(allowed(Scope.WATCHES_MANAGE_ALL, Scope.WATCHES_MANAGE_OWN))]


@router.get("/watches")
async def list_watches(request: Request, caller: Manager) -> WatchesOut:
    admin = state(request)
    book, people, triggers = admin.nestor.watch_book, People(admin.nestor.household), await Triggers.of(admin)
    watches = sorted(book.watches.values(), key=lambda w: w.created_at, reverse=True)
    return WatchesOut(
        watches=[WatchOut.of(w, people, triggers) for w in watches if reaches_watch(caller, w)],
        kinds=sorted(book.kinds),
    )


@router.get("/watches/{watch_id}")
async def get_watch(request: Request, caller: Manager, watch_id: str) -> WatchOut:
    """One active watch; 404 when unknown, ended or out of reach."""
    admin = state(request)
    watch = reachable_watch(admin, caller, watch_id)
    return WatchOut.of(watch, People(admin.nestor.household), await Triggers.of(admin))


@router.post("/watches/{watch_id}/cancel", status_code=204)
async def cancel_watch(request: Request, caller: Manager, watch_id: str) -> Response:
    admin = state(request)
    watch = reachable_watch(admin, caller, watch_id)
    await admin.nestor.watch_book.end(watch.id, "cancelled")
    return Response(status_code=204)

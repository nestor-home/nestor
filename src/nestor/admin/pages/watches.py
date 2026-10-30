"""Active watches: what the assistant is watching for, for whom, until when — and cancelling one."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.auth import Checked, LoggedIn
from nestor.admin.errors import Refused
from nestor.admin.state import state

router = APIRouter()


@router.get("/watches")
async def watches_page(request: Request, session: LoggedIn) -> HTMLResponse:
    admin = state(request)
    book = admin.nestor.watch_book
    return admin.pages.render(
        request,
        "watches.html",
        session,
        watches=sorted(book.watches.values(), key=lambda w: w.created_at, reverse=True),
        kinds=sorted(book.kinds),
        names={p.id: p.name for p in admin.nestor.household.people},
    )


@router.post("/watches/{watch_id}/cancel")
async def cancel_watch(request: Request, session: Checked, watch_id: str) -> Response:
    book = state(request).nestor.watch_book
    watch = book.watches.get(watch_id)
    if watch is None or not await book.end(watch_id, "cancelled"):
        raise Refused(404, "Veille introuvable", "Cette veille n'existe pas ou est déjà terminée.", back="/watches")
    session.notify(f"Veille « {watch.what} » annulée.")
    return RedirectResponse("/watches", status_code=303)

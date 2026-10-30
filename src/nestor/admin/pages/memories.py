"""Memories: what the assistant retains about the household, searched, corrected or forgotten."""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.pages.errors import Refused
from nestor.admin.pages.guard import Checked, LoggedIn
from nestor.admin.pages.rendering import pages_of
from nestor.admin.state import state
from nestor.core import ContractError, PersonId

router = APIRouter()

SHOWN = 100


@router.get("/memories")
async def memories_page(request: Request, session: LoggedIn, q: str = "", about: str = "") -> HTMLResponse:
    admin = state(request)
    memories = admin.nestor.memories
    person = PersonId(about) if about else None
    found = (
        await memories.recall(q, about=person, limit=SHOWN)
        if q.strip()
        else await memories.recent(about=person, limit=SHOWN)
    )
    return pages_of(request).render(
        request,
        "memories.html",
        session,
        memories=found,
        q=q,
        about=about,
        people=admin.nestor.household.people,
        names={p.id: p.name for p in admin.nestor.household.people},
        back=f"/memories?{urlencode({'q': q, 'about': about})}" if q or about else "/memories",
    )


@router.post("/memories/{memory_id}/correct")
async def correct_memory(
    request: Request,
    session: Checked,
    memory_id: str,
    text: Annotated[str, Form()] = "",
    back: Annotated[str, Form()] = "",
) -> Response:
    if not text.strip():
        raise Refused(400, "Souvenir vide", "Pour effacer un souvenir, utilisez « Oublier ».", back=_back(back))
    try:
        await state(request).nestor.memories.correct(memory_id, text)
    except ContractError:
        raise Refused(404, "Souvenir introuvable", "Ce souvenir n'existe plus.", back="/memories") from None
    session.notify("Souvenir corrigé.")
    return RedirectResponse(_back(back), status_code=303)


@router.post("/memories/{memory_id}/forget")
async def forget_memory(
    request: Request, session: Checked, memory_id: str, back: Annotated[str, Form()] = ""
) -> Response:
    try:
        memory = await state(request).nestor.memories.forget(memory_id)
    except ContractError:
        raise Refused(404, "Souvenir introuvable", "Ce souvenir n'existe plus.", back="/memories") from None
    session.notify(f"Souvenir oublié : « {memory.text} ».")
    return RedirectResponse(_back(back), status_code=303)


def _back(target: str) -> str:
    return target if target.startswith("/memories") else "/memories"

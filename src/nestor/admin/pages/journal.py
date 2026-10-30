"""The journal, readable: what happened, to whom, on which channel — and why the assistant spoke up."""

from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from nestor.admin.guard import LoggedIn
from nestor.admin.presentation import CATEGORIES, EventDescriber
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.journal import LogQuery

router = APIRouter()

PAGE = 100
SCANNED = 1000  # entries read per page before filtering by person or channel


@router.get("/journal")
async def journal_page(
    request: Request, session: LoggedIn, type: str = "", person: str = "", channel: str = "", before: str = ""
) -> HTMLResponse:
    admin = state(request)
    nestor = admin.nestor
    category = next((c for c in CATEGORIES if c.key == type), None)
    until = _moment(before)
    entries = await nestor.journal.log.read(
        LogQuery(types=category.types if category else None, until=until, limit=SCANNED, newest_first=True)
    )
    describer = EventDescriber(nestor.household, nestor.config.persona.name)
    lines, cursor = [], None
    for entry in entries:
        line = describer.describe(entry)
        cursor = line.at
        if person and PersonId(person) not in line.people:
            continue
        if channel and channel not in line.channels:
            continue
        lines.append(line)
        if len(lines) == PAGE:
            break
    filters = {"type": type, "person": person, "channel": channel}
    chosen = {k: v for k, v in filters.items() if v}
    more = len(lines) == PAGE or len(entries) == SCANNED
    older = f"/journal?{urlencode({**chosen, 'before': cursor.isoformat()})}" if more and cursor else None
    return admin.pages.render(
        request,
        "journal.html",
        session,
        lines=lines,
        categories=CATEGORIES,
        people=nestor.household.people,
        channels=sorted(c.channel_id for c in nestor.channels),
        filters=filters,
        older=older,
        names={p.id: p.name for p in nestor.household.people},
    )


def _moment(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None

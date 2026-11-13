"""The page source: each page read like `read_page`, a change of its text as an item."""

import asyncio
import difflib
import hashlib
from typing import Any

from nestor.adapters.common.text import cap
from nestor.adapters.common.web import readable
from nestor.adapters.inbound.polled import (
    Check,
    Polled,
    State,
    Watched,
)
from nestor.modules.conversation import DocumentReader
from nestor.modules.initiative import Incoming

KIND = "page"
KEPT = 100_000  # characters of a page's text kept, and compared, to show what changed
CHANGES = 2000  # characters of the changes the triage reads
BEYOND = f"(further down than the first {KEPT} characters)"


class PageSource(Polled):
    brand = "web-page"
    kind = KIND

    def __init__(self, *args: Any, reader: DocumentReader, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._reader = reader

    async def check(self, watched: Watched, known: State | None) -> Check:
        page = await readable(await self._web.get(watched.url), self._reader)
        state, changes = await asyncio.to_thread(_compared, page.text, known)
        if known is None or changes is None:
            return Check(state=state)
        item = Incoming(
            source=self.name,
            kind=KIND,
            title=page.title or watched.name,
            body=f"{watched.url}\nWhat changed on the page (- before, + now):\n{cap(changes, CHANGES)}",
            sender=watched.name,
            data={"page": watched.name, "url": watched.url},
        )
        return Check(found=[(item, state)], state=state)


def _compared(text: str, known: State | None) -> tuple[State, str | None]:
    """The page's state, and what changed since `known` line by line (`None`: nothing). The text kept and the text
    read are compared on the same first `KEPT` characters; a change only further down is said to be there."""
    state = {"digest": hashlib.sha256(text.encode()).hexdigest(), "text": text[:KEPT]}
    if known is None or known.get("digest") == state["digest"]:
        return state, None
    diff = difflib.unified_diff(str(known.get("text", "")).splitlines(), state["text"].splitlines(), n=0, lineterm="")
    lines = [f"{line[0]} {line[1:]}" for line in list(diff)[2:] if not line.startswith("@@")]  # past the two headers
    return state, "\n".join(lines) or BEYOND

"""What the central agent sees of the map of itself: one tool to consult it, and one line saying when."""

import re
from collections.abc import Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Tool, ToolContext, ToolProvider
from nestor.modules.conversation import ContextProvider, Sections, TurnContext
from nestor.modules.system.selfmap.ports import Documentation
from nestor.modules.system.selfmap.service import SelfMap, describe

GUIDANCE = (
    "Before saying you cannot do something, and when asked what you can do, connect or use, or how to set something "
    "up, call about_nestor: it says what you are made of here, what could be added and where it is documented."
)
EXCERPT = 3000  # characters of a page the answer carries
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
OFFLINE = "The documentation could not be read now: this comes from the map alone; say so if it matters."
NOTHING = "No part matches the question's words: the overview names every part."


class AboutNestor(ToolProvider, ContextProvider):
    name = "about-nestor"

    def __init__(self, parts: SelfMap, docs: Documentation | None = None) -> None:
        self.map, self.docs = parts, docs

    def tools(self) -> Sequence[Tool]:
        question = {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "in English, with the words of what is wanted: 'be notified by a webhook', "
                    "'hand over a long task', 'read my calendar'",
                }
            },
            "required": ["question"],
        }
        return (
            Tool(
                spec=ToolSpec(
                    "about_nestor",
                    "What you (Nestor) are made of here: the parts plugged in, those installed but not configured, "
                    "those that could be added, what each needs, and the documentation of the closest.",
                    question,
                ),
                run=self._about,
                timeout_s=15.0,
            ),
        )

    def guidance(self) -> str:
        return GUIDANCE

    async def context(self, turn: TurnContext) -> Sections:
        return {}

    async def _about(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        parts = self.map.relevant(str(arguments.get("question", "")))
        answer: dict[str, object] = {
            "overview": self.map.overview(),
            "relevant": "\n".join(describe(p) for p in parts) or NOTHING,
        }
        if parts and self.docs is not None:
            card = parts[0].card
            try:
                page = await self.docs.page(card.page)
            except ProviderError:
                answer["docs"] = OFFLINE
            else:
                answer["docs"] = f"From {card.url}:\n{excerpt(page, card.section)}"
        return answer


def excerpt(page: str, section: str | None) -> str:
    """The section of a Markdown page whose heading has that anchor (down to the next heading of its level or
    above), else the page from its start; cut to `EXCERPT` characters."""
    lines = page.splitlines()
    headings: list[tuple[int, int, str]] = []  # line, level, anchor; never a comment in a code block
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and (heading := _HEADING.match(line)):
            headings.append((index, len(heading.group(1)), anchor(heading.group(2))))
    start, end = 0, len(lines)
    found = next((h for h in headings if section and h[2] == section), None)
    if found is not None:
        start = found[0]
        end = next((i for i, level, _ in headings if i > start and level <= found[1]), end)
    text = "\n".join(lines[start:end]).strip()
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1].rstrip() + "…"


def anchor(heading: str) -> str:
    """A heading's anchor as the site writes it: lower case, punctuation dropped, spaces as hyphens."""
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", heading.strip().lower()))

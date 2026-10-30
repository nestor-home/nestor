"""What the central agent sees of watches: tools to create, list and cancel them, and the active ones."""

from collections.abc import Mapping, Sequence
from datetime import timedelta

from nestor.core import utc_now
from nestor.modules.channels import Address
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider
from nestor.modules.household import Person
from nestor.modules.initiative.watches.book import WatchBook
from nestor.modules.initiative.watches.types import Watch

HOW_TO_WATCH = (
    "When someone asks to be told when something arrives or happens (a parcel, an email from someone, an answer), "
    "call create_watch with their words and a few distinctive keywords (sender, carrier, tracking number, subject "
    "words). Confirm briefly. When it matches you will be asked to announce it. Watches can see: {kinds}."
)
NO_SOURCE = "No inbound source is connected (no mailbox): you cannot watch for anything. Say so if asked."


class WatchTools(ToolProvider, ContextProvider):
    name = "watch-tools"

    def __init__(self, book: WatchBook) -> None:
        self.book = book

    def tools(self) -> Sequence[Tool]:
        kinds = sorted(self.book.kinds)
        if not kinds:
            return ()
        create = {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "what to watch for, in the person's words"},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "distinctive words"},
                "kinds": {"type": "array", "items": {"type": "string", "enum": kinds}},
                "once": {"type": "boolean", "description": "end after the first match (default true)"},
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "description": "how long to keep watching"},
            },
            "required": ["what", "keywords"],
        }
        cancel = {"type": "object", "properties": {"watch_id": {"type": "string"}}, "required": ["watch_id"]}
        return (
            Tool(
                spec=ToolSpec("create_watch", "Watch incoming items for something.", create),
                run=self._create,
                risk=Risk.WRITE,
            ),
            Tool(spec=ToolSpec("list_watches", "The active watches."), run=self._list),
            Tool(spec=ToolSpec("cancel_watch", "Stop a watch.", cancel), run=self._cancel, risk=Risk.WRITE),
        )

    async def context(self, person: Person | None, address: Address) -> str | None:
        if not self.book.kinds:
            return NO_SOURCE
        lines = [HOW_TO_WATCH.format(kinds=", ".join(sorted(self.book.kinds)))]
        if self.book.watches:
            listed = "\n".join(f"- [{w.id}] {w.what}" for w in self.book.watches.values())
            lines.append(f"Active watches:\n{listed}")
        return "\n\n".join(lines)

    async def _create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        keywords = arguments.get("keywords") or []
        kinds = arguments.get("kinds") or sorted(self.book.kinds)
        if not isinstance(keywords, list) or not isinstance(kinds, list):
            raise ToolFailed("keywords and kinds must be lists")
        unknown = set(map(str, kinds)) - self.book.kinds
        if unknown:
            raise ToolFailed(f"cannot watch {', '.join(sorted(unknown))}: no such source connected")
        days = arguments.get("days")
        watch = await self.book.create(
            Watch(
                what=str(arguments["what"]),
                keywords=tuple(str(k) for k in keywords if str(k).strip()),
                kinds=tuple(str(k) for k in kinds),
                once=arguments.get("once") is not False,
                owner=context.person,
                created_in=context.address,
                until=utc_now() + timedelta(days=int(days)) if isinstance(days, int) else None,
            )
        )
        return {"watch_id": watch.id, "watching": watch.what}

    async def _list(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        return {
            "watches": [
                {"watch_id": w.id, "what": w.what, "keywords": list(w.keywords)} for w in self.book.watches.values()
            ]
        }

    async def _cancel(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        if not await self.book.end(str(arguments["watch_id"]), "cancelled"):
            raise ToolFailed(f"no active watch {arguments['watch_id']!r}")
        return {"cancelled": True}

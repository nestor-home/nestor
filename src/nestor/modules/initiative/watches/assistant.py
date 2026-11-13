"""What the central agent sees of watches: tools to create, list and cancel them, and the active ones."""

from collections.abc import Mapping, Sequence
from datetime import timedelta

from nestor.core import utc_now
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.initiative.watches.book import WatchBook
from nestor.modules.initiative.watches.types import Watch

HOW_TO_WATCH = (
    "When someone asks to be told when something arrives or happens (a parcel, an email from someone, an answer, a "
    "release in a news feed, a price on a web page), call create_watch with what to watch for, in their words, precise "
    "enough to recognise it (sender, carrier, tracking number, the feed or page by its name, the threshold…), and the "
    "kinds it can come as. Confirm briefly. When it matches you will be asked to announce it. "
    "Watches can see:\n{kinds}\n"
    "Only these: a feed or a page that is not listed is added to the configuration by the household, not by you."
)
NO_SOURCE = "No inbound source is connected (no mailbox, feed or page): you cannot watch for anything. Say so if asked."


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
                "kinds": {"type": "array", "items": {"type": "string", "enum": kinds}},
                "once": {"type": "boolean", "description": "end after the first match (default true)"},
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "description": "how long to keep watching"},
            },
            "required": ["what"],
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

    def guidance(self) -> str:
        if not self.book.kinds:
            return NO_SOURCE
        kinds = (
            f"- {kind}: {', '.join(followed)}" if followed else f"- {kind}"
            for kind, followed in sorted(self.book.kinds.items())
        )
        return HOW_TO_WATCH.format(kinds="\n".join(kinds))

    async def context(self, turn: TurnContext) -> Sections:
        if not self.book.watches:
            return {}
        listed = "\n".join(f"- [{w.id}] {w.what}" for w in self.book.watches.values())
        return {Layer.HOUSEHOLD: f"Active watches:\n{listed}"}  # they change when one is created or ends

    async def _create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        kinds = arguments.get("kinds") or sorted(self.book.kinds)
        if not isinstance(kinds, list):
            raise ToolFailed("kinds must be a list")
        unknown = set(map(str, kinds)) - self.book.kinds.keys()
        if unknown:
            raise ToolFailed(f"cannot watch {', '.join(sorted(unknown))}: no such source connected")
        days = arguments.get("days")
        watch = await self.book.create(
            Watch(
                what=str(arguments["what"]),
                kinds=tuple(str(k) for k in kinds),
                once=arguments.get("once") is not False,
                owner=context.person,
                created_in=context.address,
                until=utc_now() + timedelta(days=int(days)) if isinstance(days, int) else None,
            ),
            exchange=context.exchange,
        )
        return {"watch_id": watch.id, "watching": watch.what}

    async def _list(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        return {"watches": [{"watch_id": w.id, "what": w.what} for w in self.book.watches.values()]}

    async def _cancel(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        if not await self.book.end(str(arguments["watch_id"]), "cancelled"):
            raise ToolFailed(f"no active watch {arguments['watch_id']!r}")
        return {"cancelled": True}

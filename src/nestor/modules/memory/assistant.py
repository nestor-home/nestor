"""What the central agent sees of memory: what it remembers and what its past conversations with whoever speaks
were about, and tools to remember, recall (with dates), reread a conversation, correct and forget."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Medium
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.household import Household
from nestor.modules.journal import Journal
from nestor.modules.memory.episodes import Episode, Episodes
from nestor.modules.memory.episodes.transcript import transcript
from nestor.modules.memory.recall import RecallSettings, for_turn
from nestor.modules.memory.service import Memories
from nestor.modules.memory.types import Memory

HOUSEHOLD = "household"


HOW_TO_REMEMBER = (
    "When someone asks you to remember something, or shares a lasting fact or preference, call remember with one "
    "short self-contained sentence. The memories that seem to matter to this turn are listed with it, and so are "
    "the past conversations of whoever speaks: their latest ones, and older ones that seem to matter. When a "
    "question may depend on something said earlier and it is not listed, call recall, with since and until for "
    'a time ("last week": compute the dates from now); to know exactly what was said in a conversation, call '
    "read_conversation with its id. Each memory is dated: when two disagree, the later one holds, and you may "
    "correct or forget the earlier. Correct or forget a memory when asked, by its id. Never invent a memory."
)


class MemoryTools(ToolProvider, ContextProvider):
    name = "memory"

    def __init__(
        self,
        memories: Memories,
        episodes: Episodes,
        household: Household,
        journal: Journal,
        *,
        assistant: str,
        timezone: str = "UTC",
        recall: RecallSettings | None = None,
    ) -> None:
        self.memories, self.episodes, self.household, self.journal = memories, episodes, household, journal
        self.assistant, self.timezone = assistant, timezone
        self.recall = recall or RecallSettings()

    def tools(self) -> Sequence[Tool]:
        about = {
            "type": "string",
            "enum": [HOUSEHOLD, *(p.id for p in self.household.people)],
            "description": "who the memory is about; household when it concerns everyone",
        }
        identified = {"type": "object", "properties": {"memory_id": {"type": "string"}}, "required": ["memory_id"]}
        return (
            Tool(
                spec=ToolSpec(
                    "remember",
                    "Keep a lasting fact or preference.",
                    {
                        "type": "object",
                        "properties": {"text": {"type": "string"}, "about": about},
                        "required": ["text", "about"],
                    },
                ),
                run=self._remember,
                risk=Risk.WRITE,
            ),
            Tool(
                spec=ToolSpec(
                    "recall",
                    "Search what you were told before: memories, and past conversations with whoever speaks.",
                    {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "what to look for; empty for a time only"},
                            "about": about,
                            "since": {"type": "string", "description": "conversations ended from: 2026-10-26"},
                            "until": {"type": "string", "description": "until, included: 2026-11-01"},
                        },
                        "required": ["query"],
                    },
                ),
                run=self._recall,
            ),
            Tool(
                spec=ToolSpec(
                    "read_conversation",
                    "Reread a past conversation word for word, by its id.",
                    {
                        "type": "object",
                        "properties": {"conversation_id": {"type": "string"}},
                        "required": ["conversation_id"],
                    },
                ),
                run=self._read_conversation,
            ),
            Tool(
                spec=ToolSpec(
                    "correct_memory",
                    "Replace the text of a memory.",
                    {
                        "type": "object",
                        "properties": {"memory_id": {"type": "string"}, "text": {"type": "string"}},
                        "required": ["memory_id", "text"],
                    },
                ),
                run=self._correct,
                risk=Risk.WRITE,
            ),
            Tool(spec=ToolSpec("forget", "Forget a memory for good.", identified), run=self._forget, risk=Risk.WRITE),
        )

    def guidance(self) -> str:
        return HOW_TO_REMEMBER

    async def context(self, turn: TurnContext) -> Sections:
        """The latest memories with the household (they change now and then, so the cache keeps them); with this
        turn, what was said finds among the others, and the past conversations of whoever speaks."""
        person = turn.person.id if turn.person else None
        found = await for_turn(self.memories, self.episodes, turn.said, person, self.recall)
        sections: dict[Layer, str] = {}
        if found.shown:
            sections[Layer.HOUSEHOLD] = f"What you remember, the latest first:\n{self._lines(found.shown)}"
        parts = []
        if found.found:
            parts.append(f"Older memories that may matter here:\n{self._lines(found.found)}")
        if found.latest_episodes:
            parts.append(f"Your latest conversations with them:\n{self._episodes(found.latest_episodes)}")
        if found.found_episodes:
            parts.append(f"Older conversations with them that may matter here:\n{self._episodes(found.found_episodes)}")
        if parts:
            sections[Layer.TURN] = "\n\n".join(parts)
        return sections

    def _lines(self, memories: Sequence[Memory]) -> str:
        return "\n".join(f"- [{m.id}] {self._line(m)}" for m in memories)

    def _episodes(self, episodes: Sequence[Episode]) -> str:
        zone = ZoneInfo(self.timezone)
        return "\n".join(
            f"- [{e.id}] {e.ended_at.astimezone(zone):%A %d %B %Y, %H:%M}, "
            f"{'aloud' if e.medium is Medium.SPOKEN else 'in writing'} ({e.address}): {e.summary}"
            for e in episodes
        )

    async def _remember(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        memory = await self.memories.remember(
            str(arguments["text"]),
            about=self._about(arguments),
            source=context.address,
            told_by=context.person,
            exchange=context.exchange,
        )
        return {"memory_id": memory.id, "remembered": memory.text}

    async def _recall(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        query = str(arguments.get("query") or "").strip()
        since, until = self._bound(arguments.get("since"), end=False), self._bound(arguments.get("until"), end=True)
        vector = await self.memories.query(query) if query else None
        memories = await self.memories.recall(query, vector=vector, about=self._about(arguments)) if query else []
        conversations: list[Episode] = []
        if context.person is not None:
            conversations = (
                await self.episodes.recall(
                    query, vector=vector, person=context.person, limit=8, since=since, until=until
                )
                if query
                else await self.episodes.recent(context.person, limit=8, since=since, until=until)
            )
        return {
            "memories": [{"memory_id": m.id, "text": self._line(m)} for m in memories],
            "conversations": self._episodes(conversations) or "none",
        }

    async def _read_conversation(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        conversation = str(arguments["conversation_id"])
        (episode,) = await self.episodes.store.get_many([conversation]) or (None,)
        if episode is None or context.person not in episode.participants:
            raise ToolFailed(f"no conversation {conversation} that you can reread with this person")
        lines = await transcript(
            self.journal,
            self.household,
            address=episode.address,
            conversation=conversation,
            since=episode.started_at,
            assistant=self.assistant,
            timezone=self.timezone,
        )
        return {"conversation": "\n".join(lines)}

    async def _correct(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        try:
            memory = await self.memories.correct(
                str(arguments["memory_id"]), str(arguments["text"]), by=context.person, exchange=context.exchange
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"memory_id": memory.id, "now": memory.text}

    async def _forget(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        try:
            memory = await self.memories.forget(
                str(arguments["memory_id"]), by=context.person, exchange=context.exchange
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"forgotten": memory.text}

    def _about(self, arguments: Mapping[str, object]) -> PersonId | None:
        about = arguments.get("about")
        if about in (None, "", HOUSEHOLD):
            return None
        try:
            return self.household.person(PersonId(str(about))).id
        except ContractError:
            raise ToolFailed(f"{about!r} is not a member of the household") from None

    def _bound(self, value: object, *, end: bool) -> datetime | None:
        """A date or a date and time in the household's clock; a date alone `until` takes the whole day."""
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            raise ToolFailed(f"cannot read the date {value!r}: write it as 2026-11-01 or 2026-11-01T18:00") from None
        if end and len(str(value)) <= len("2026-11-01"):
            parsed += timedelta(days=1) - timedelta(microseconds=1)
        return parsed.replace(tzinfo=ZoneInfo(self.timezone)) if parsed.tzinfo is None else parsed

    def _line(self, memory: Memory) -> str:
        """Dated, so that of two memories that disagree the model can tell the later one."""
        dated = f"{memory.updated_at:%Y-%m-%d}"
        if memory.about is None:
            return f"{dated} {memory.text}"
        name = next((p.name for p in self.household.people if p.id == memory.about), memory.about)
        return f"{dated} (about {name}) {memory.text}"

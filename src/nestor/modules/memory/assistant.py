"""What the central agent sees of memory: what it remembers, by place, and what its past conversations with whoever
speaks were about, and tools to remember, recall (by place, with dates), reread a conversation, move, correct and
forget, and keep a task's note as a memory."""

import asyncio
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.household import Household
from nestor.modules.journal import Journal
from nestor.modules.memory.episodes import Episode, Episodes
from nestor.modules.memory.episodes.transcript import transcript
from nestor.modules.memory.recall import RecallSettings, for_turn
from nestor.modules.memory.service import Memories, named, placed
from nestor.modules.memory.ties import Ties
from nestor.modules.memory.types import Memory, Place, Shelf

type TaskNotes = Callable[[str, PersonId | None], Sequence[str] | None]
"""The notes of a task (by id) that the person owns; `None` when there is no such task of theirs."""

HOW_TO_REMEMBER = (
    "When someone asks you to remember something, or shares a lasting fact or preference, call remember with one "
    "short self-contained sentence, filed in its place: people/<id> for one person, home for the house itself "
    "(rooms, devices, appliances, works done), household for the family's shared life (routines, pets, contacts, "
    "rules), projects/<name> for something with an end (a renovation, a trip, a purchase), topics/<name> for a lasting "
    "interest (the garden, wine). Reuse a project or topic already listed; name a new one in a few lowercase words "
    "joined by hyphens. The memories that seem to matter to this turn are listed "
    "with it, and so are the past conversations of whoever speaks: their latest ones, and older ones that seem to "
    "matter. When a question may depend on something said earlier and it is not listed, call recall, with a place "
    'and since and until for a time ("last week": compute the dates from now); to know exactly what was said in a '
    "conversation, call read_conversation with its id. Each memory is dated: when two disagree, the later one holds, "
    "and you may correct or forget the earlier. Move, correct or forget a memory when asked, by its id. Never invent "
    "a memory."
)
HOW_TO_TIE = (
    "When a memory only holds while a {kinds} runs (a price to watch, a search going on), tie it to it: it is retired "
    "when that ends."
)
HOW_TO_KEEP_NOTES = (
    "An executor's notes belong to its task: keep one as a memory with keep_note only when it matters beyond the task."
)
SHELVES = list(Shelf)  # the order places are listed in


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
        ties: Ties | None = None,
        notes: TaskNotes | None = None,
    ) -> None:
        self.memories, self.episodes, self.household, self.journal = memories, episodes, household, journal
        self.assistant, self.timezone = assistant, timezone
        self.recall = recall or RecallSettings()
        self.ties, self.task_notes = ties, notes

    def tools(self) -> Sequence[Tool]:
        people = ", ".join(p.id for p in self.household.people)
        place = {
            "type": "string",
            "description": f"people/<id> (ids: {people}), home, household, projects/<name> or topics/<name>",
        }
        identified = {"type": "object", "properties": {"memory_id": {"type": "string"}}, "required": ["memory_id"]}
        remembered: dict[str, object] = {"text": {"type": "string"}, "place": place}
        if self.ties and self.ties.kinds:
            kinds = " or ".join(f"{k}:<id>" for k in self.ties.kinds)
            remembered["tied_to"] = {"type": "string", "description": f"{kinds}: retired when that one ends"}
        tools = [
            Tool(
                spec=ToolSpec(
                    "remember",
                    "Keep a lasting fact or preference, filed in its place.",
                    {"type": "object", "properties": remembered, "required": ["text", "place"]},
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
                            "place": {
                                "type": "string",
                                "description": "only the memories of this place, or of a shelf: projects, topics",
                            },
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
                    "move_memory",
                    "File a memory in another place.",
                    {
                        "type": "object",
                        "properties": {"memory_id": {"type": "string"}, "place": place},
                        "required": ["memory_id", "place"],
                    },
                ),
                run=self._move,
                risk=Risk.WRITE,
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
        ]
        if self.task_notes is not None:
            tools.append(
                Tool(
                    spec=ToolSpec(
                        "keep_note",
                        "Keep one of a task's notes (read_task lists them, numbered from 1) as a memory, when it "
                        "matters beyond the task.",
                        {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string"},
                                "note": {"type": "integer", "minimum": 1},
                                "text": {
                                    "type": "string",
                                    "description": "the note as one short self-contained sentence",
                                },
                                "place": place,
                            },
                            "required": ["task", "note", "text", "place"],
                        },
                    ),
                    run=self._keep_note,
                    risk=Risk.WRITE,
                )
            )
        return tools

    def guidance(self) -> str:
        parts = [HOW_TO_REMEMBER]
        if self.ties and self.ties.kinds:
            parts.append(HOW_TO_TIE.format(kinds=" or ".join(self.ties.kinds)))
        if self.task_notes is not None:
            parts.append(HOW_TO_KEEP_NOTES)
        return " ".join(parts)

    async def context(self, turn: TurnContext) -> Sections:
        """The latest memories with the household (they change now and then, so the cache keeps them); with this
        turn, what was said finds among the others, and the past conversations of whoever speaks."""
        person = turn.person.id if turn.person else None
        found = await for_turn(self.memories, self.episodes, turn.said, person, self.recall)
        sections: dict[Layer, str] = {}
        if found.shown:
            sections[Layer.HOUSEHOLD] = f"What you remember, by place, the latest first:\n{self._shelved(found.shown)}"
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

    def _shelved(self, memories: Sequence[Memory]) -> str:
        """Grouped by place: the people in the household's order, then the home, the household, the projects and
        the topics by name; the latest first in each."""
        by_place: dict[Place, list[Memory]] = defaultdict(list)
        for memory in memories:
            by_place[memory.place].append(memory)
        order = {p.id: i for i, p in enumerate(self.household.people)}
        places = sorted(
            by_place,
            key=lambda p: (SHELVES.index(p.shelf), order.get(PersonId(p.name or ""), len(order)), p.name or ""),
        )
        return "\n".join(
            f"{self._place(place)}:\n" + "\n".join(f"- [{m.id}] {self._dated(m)}" for m in by_place[place])
            for place in places
        )

    def _place(self, place: Place) -> str:
        return named(place, self.household)

    def _episodes(self, episodes: Sequence[Episode]) -> str:
        zone = ZoneInfo(self.timezone)
        return "\n".join(f"- [{e.id}] {e.describe(zone)}: {e.summary}" for e in episodes)

    async def _remember(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        return await self.keep(
            str(arguments["text"]),
            place=self._placed(arguments.get("place")),
            source=context.address,
            told_by=context.person,
            exchange=context.exchange,
            tied_to=self._tied(arguments.get("tied_to")),
        )

    async def keep(
        self,
        text: str,
        *,
        place: Place,
        source: Address | None,
        told_by: PersonId | None = None,
        exchange: Exchange | None = None,
        tied_to: str | None = None,
        task: str | None = None,
    ) -> Mapping[str, object]:
        """Keep a lasting fact in its `place`, as the `remember` tool does."""
        memory = await self.memories.remember(
            text, place=place, source=source, told_by=told_by, exchange=exchange, tied_to=tied_to, task=task
        )
        return {"memory_id": memory.id, "remembered": memory.text, "place": str(memory.place)}

    async def _keep_note(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = str(arguments.get("task") or "")
        notes = self.task_notes(task, context.person) if self.task_notes else None
        if notes is None:
            raise ToolFailed(f"no task {task!r} of theirs: list_tasks names them")
        number = arguments.get("note")
        if not isinstance(number, int) or not 1 <= number <= len(notes):
            raise ToolFailed(f"task {task} has {len(notes)} notes, numbered from 1")
        return await self.keep(
            str(arguments.get("text") or notes[number - 1]),
            place=self._placed(arguments.get("place")),
            source=context.address,
            told_by=context.person,
            exchange=context.exchange,
            task=task,
        )

    async def _recall(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        return await self.search(
            str(arguments.get("query") or "").strip(),
            person=context.person,
            place=self._placed(arguments["place"]) if arguments.get("place") else None,
            since=self.bound(arguments.get("since"), end=False),
            until=self.bound(arguments.get("until"), end=True),
        )

    async def search(
        self,
        query: str,
        *,
        person: PersonId | None,
        about: PersonId | None = None,
        place: Place | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Mapping[str, object]:
        """The memories matching `query` (`about` someone and shared, of a `place` or a shelf; any when `None`) and
        `person`'s past conversations, as the `recall` tool gives them; an empty query gives their latest
        conversations."""
        memories: list[Memory] = []
        conversations: list[Episode] = []
        if not query:
            conversations = await self.episodes.recent(person, limit=8, since=since, until=until) if person else []
        else:
            vector = asyncio.create_task(self.memories.query(query))
            try:
                memories = await self.memories.recall(query, vector=vector, about=about, place=place)
                if person is not None:
                    conversations = await self.episodes.recall(
                        query, vector=vector, person=person, limit=8, since=since, until=until
                    )
            finally:
                vector.cancel()
        return {
            "memories": [{"memory_id": m.id, "text": self._line(m)} for m in memories],
            "conversations": self._episodes(conversations) or "none",
        }

    async def _read_conversation(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        conversation = str(arguments["conversation_id"])
        episode = await self.episodes.find(conversation)
        if episode is None or context.person not in episode.participants:
            raise ToolFailed(f"no conversation {conversation} that you can reread with this person")
        lines = await transcript(
            self.journal,
            self.household,
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

    async def _move(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        place = self._placed(arguments.get("place"))
        memory_id = str(arguments["memory_id"])
        found = await self.memories.store.get(memory_id)
        if found is not None and found.place.person not in (None, context.person):
            # out of a person's place, it would be shared with the whole household
            raise ToolFailed(f"only {found.place.person} moves what is filed in {found.place}")
        try:
            memory = await self.memories.move(memory_id, place, by=context.person, exchange=context.exchange)
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"memory_id": memory.id, "place": str(memory.place)}

    def _placed(self, value: object) -> Place:
        """A place the model named, checked: a person's must be a member of the household."""
        try:
            return placed(str(value or ""), self.household)
        except ContractError as error:
            raise ToolFailed(f"{value!r} is not a place: {error}") from None

    def _tied(self, value: object) -> str | None:
        if not value:
            return None
        if self.ties is None:
            raise ToolFailed("memories cannot be tied to anything here")
        try:
            return self.ties.check(str(value))
        except ContractError as error:
            raise ToolFailed(str(error)) from None

    def bound(self, value: object, *, end: bool) -> datetime | None:
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
        """Dated and placed, so that of two memories that disagree the model can tell the later one."""
        return f"{self._dated(memory)} ({self._place(memory.place)})"

    def _dated(self, memory: Memory) -> str:
        tied = f" (while {memory.tied_to} runs)" if memory.tied_to else ""
        return f"{memory.updated_at:%Y-%m-%d} {memory.text}{tied}"

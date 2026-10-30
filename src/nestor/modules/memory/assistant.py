"""What the central agent sees of memory: four tools and what it currently remembers."""

from collections.abc import Mapping, Sequence

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider
from nestor.modules.household import Household, Person
from nestor.modules.memory.service import Memories
from nestor.modules.memory.types import Memory

HOUSEHOLD = "household"
HOW_TO_REMEMBER = (
    "When someone asks you to remember something, or shares a lasting fact or preference, call remember with one "
    "short self-contained sentence. When a question may depend on something you were told earlier and it is not "
    "listed below, call recall. Correct or forget a memory when asked, by its id. Never invent a memory."
)


class MemoryTools(ToolProvider, ContextProvider):
    name = "memory"

    def __init__(self, memories: Memories, household: Household, *, shown: int = 30) -> None:
        self.memories, self.household, self._shown = memories, household, shown

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
                    "Search what you were told before.",
                    {
                        "type": "object",
                        "properties": {"query": {"type": "string"}, "about": about},
                        "required": ["query"],
                    },
                ),
                run=self._recall,
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

    async def context(self, person: Person | None, address: Address) -> str | None:
        known = await self.memories.recent(limit=self._shown)
        if not known:
            return f"{HOW_TO_REMEMBER}\n\nYou do not remember anything yet."
        lines = "\n".join(f"- [{m.id}] {self._line(m)}" for m in known)
        return f"{HOW_TO_REMEMBER}\n\nWhat you remember, most recent first:\n{lines}"

    async def _remember(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        memory = await self.memories.remember(
            str(arguments["text"]), about=self._about(arguments), source=context.address, told_by=context.person
        )
        return {"memory_id": memory.id, "remembered": memory.text}

    async def _recall(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        found = await self.memories.recall(str(arguments["query"]), about=self._about(arguments))
        return {"memories": [{"memory_id": m.id, "text": self._line(m)} for m in found]}

    async def _correct(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        try:
            memory = await self.memories.correct(str(arguments["memory_id"]), str(arguments["text"]), by=context.person)
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"memory_id": memory.id, "now": memory.text}

    async def _forget(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        try:
            memory = await self.memories.forget(str(arguments["memory_id"]), by=context.person)
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

    def _line(self, memory: Memory) -> str:
        if memory.about is None:
            return memory.text
        name = next((p.name for p in self.household.people if p.id == memory.about), memory.about)
        return f"(about {name}) {memory.text}"

"""Memory: remembered from one conversation, reused in another, corrected and forgotten."""

from collections.abc import Mapping

import pytest

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address, InboundMessage, Sender
from nestor.modules.cognition.model import ToolCall
from nestor.modules.cognition.tools import Toolbox, ToolContext, ToolFailed
from nestor.modules.conversation import Agent, Persona
from nestor.modules.household import Account, Household, Person
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories, MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.memory.assistant import MemoryTools
from nestor.testing.cognition import ScriptedModel
from nestor.testing.journal import MemoryEventLog
from nestor.testing.memory import InMemoryMemoryStore, MemoryStoreContract

VOICE, TELEGRAM = Address("voice", "salon"), Address("telegram", "42")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("voice:*"), Account.parse("telegram:42")))
MATHILDE = Person(id=PersonId("mathilde"), name="Mathilde")
HOUSEHOLD = Household([MATHIS, MATHILDE])


class TestInMemoryMemoryStore(MemoryStoreContract):
    def store(self) -> InMemoryMemoryStore:
        return InMemoryMemoryStore()


async def test_the_contract_rejects_a_store_that_ignores_accents_badly() -> None:
    class Literal(InMemoryMemoryStore):
        async def search(self, query: str, *, about: PersonId | None = None, limit: int = 10) -> list:
            return [m for m in self.memories.values() if query in m.text]

    class Suite(MemoryStoreContract):
        def store(self) -> InMemoryMemoryStore:
            return Literal()

    with pytest.raises(AssertionError):
        await Suite().test_a_memory_is_found_by_its_words_whatever_the_accents()


@pytest.fixture
def memories() -> Memories:
    return Memories(Journal(MemoryEventLog()), InMemoryMemoryStore())


async def test_every_change_is_logged_before_it_applies(memories: Memories) -> None:
    memory = await memories.remember(" Mathilde est végétarienne ", about=MATHILDE.id, source=VOICE, told_by=MATHIS.id)
    await memories.correct(memory.id, "Mathilde est végane", by=MATHIS.id)
    await memories.forget(memory.id, by=MATHIS.id)

    journal = memories.journal
    recorded = (await journal.history(MemoryRecorded))[0]
    assert (recorded.text, recorded.about, recorded.learnt_in, recorded.told_by) == (
        "Mathilde est végétarienne",
        "mathilde",
        VOICE,
        "mathis",
    )
    assert [e.text for e in await journal.history(MemoryCorrected)] == ["Mathilde est végane"]
    assert len(await journal.history(MemoryForgotten)) == 1
    assert await memories.recall("Mathilde") == []


async def test_unknown_or_empty_memories_are_refused(memories: Memories) -> None:
    with pytest.raises(ContractError, match="needs some text"):
        await memories.remember("   ")
    with pytest.raises(ContractError, match="no memory"):
        await memories.forget("nope")


def agent(journal: Journal, tools: MemoryTools, model: ScriptedModel) -> Agent:
    return Agent(
        model=model,
        persona=Persona(name="Richie", character="Tu es Richie."),
        journal=journal,
        household=HOUSEHOLD,
        toolbox=Toolbox(journal, providers=[tools]),
        context=[tools],
    )


async def test_a_fact_told_by_voice_is_known_later_on_telegram() -> None:
    journal = Journal(MemoryEventLog())
    tools = MemoryTools(Memories(journal, InMemoryMemoryStore()), HOUSEHOLD)
    remember = ToolCall("c1", "remember", {"text": "Mathilde est végétarienne", "about": "mathilde"})
    told = agent(journal, tools, ScriptedModel(remember, "C'est noté."))
    await told.respond(
        InboundMessage(address=VOICE, sender=Sender("mic"), text="Retiens que Mathilde est végétarienne")
    ).collect()

    model = ScriptedModel("Une poêlée de légumes, sans viande pour Mathilde.")
    later = agent(journal, tools, model)
    await later.respond(
        InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Je cuisine quoi ce soir ?")
    ).collect()

    instructions = model.requests[0].messages[0].content
    assert "(about Mathilde) Mathilde est végétarienne" in instructions
    assert [m.content for m in model.requests[0].messages[1:]] == ["Je cuisine quoi ce soir ?"]


async def test_the_tools_recall_correct_and_forget_by_id() -> None:
    memories = Memories(Journal(MemoryEventLog()), InMemoryMemoryStore())
    tools = {t.name: t for t in MemoryTools(memories, HOUSEHOLD).tools()}
    context = ToolContext(address=TELEGRAM, person=MATHIS.id)

    def data(output: object) -> Mapping[str, object]:
        assert isinstance(output, Mapping)
        return output

    saved = data(
        await tools["remember"].run({"text": "Le portail s'ouvre avec le code 1234", "about": "household"}, context)
    )
    found = data(await tools["recall"].run({"query": "code du portail"}, context))
    assert found["memories"] == [{"memory_id": saved["memory_id"], "text": "Le portail s'ouvre avec le code 1234"}]

    await tools["correct_memory"].run({"memory_id": saved["memory_id"], "text": "Le code du portail est 4321"}, context)
    assert data(await tools["forget"].run({"memory_id": saved["memory_id"]}, context)) == {
        "forgotten": "Le code du portail est 4321"
    }
    for name, arguments in [
        ("forget", {"memory_id": "nope"}),
        ("correct_memory", {"memory_id": "nope", "text": "x"}),
        ("remember", {"text": "x", "about": "voisin"}),
    ]:
        with pytest.raises(ToolFailed):
            await tools[name].run(arguments, context)


async def test_with_nothing_remembered_the_agent_is_told_so() -> None:
    tools = MemoryTools(Memories(Journal(MemoryEventLog()), InMemoryMemoryStore()), HOUSEHOLD)
    assert "You do not remember anything yet." in str(await tools.context(MATHIS, TELEGRAM))

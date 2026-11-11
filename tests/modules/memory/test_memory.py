"""Memory: remembered from one conversation, reused in another, corrected and forgotten."""

from collections.abc import Mapping

import pytest

from nestor.core import ContractError, Event, PersonId, ProviderError, utc_now
from nestor.modules.channels import Address, InboundMessage, Sender
from nestor.modules.cognition.model import ToolCall
from nestor.modules.cognition.tools import Toolbox, ToolContext, ToolFailed
from nestor.modules.conversation import Agent, Attachments, Layer, ModelChoice, Persona, TurnContext
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories, MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.memory.assistant import MemoryTools
from nestor.modules.memory.episodes import Episodes
from nestor.modules.memory.recall import RecallSettings
from nestor.testing.cognition import ScriptedModel
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog
from nestor.testing.memory import InMemoryEpisodeStore, InMemoryMemoryStore, MemoryStoreContract

VOICE, TELEGRAM = Address("voice", "salon"), Address("telegram", "42")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),))
MATHILDE = Person(id=PersonId("mathilde"), name="Mathilde")
HOUSEHOLD = Household([MATHIS, MATHILDE])


class TestInMemoryMemoryStore(MemoryStoreContract):
    def store(self) -> InMemoryMemoryStore:
        return InMemoryMemoryStore()


async def test_the_contract_rejects_a_store_that_ignores_accents_badly() -> None:
    class AccentBound(InMemoryMemoryStore):
        """Matches words whatever their case, but only with the same accents."""

        async def search(self, query: str, *, about: PersonId | None = None, limit: int = 10) -> list:
            wanted = set(query.casefold().split())
            return [m for m in self.memories.values() if wanted & set(m.text.casefold().split())]

    class Suite(MemoryStoreContract):
        def store(self) -> InMemoryMemoryStore:
            return AccentBound()

    with pytest.raises(AssertionError):
        await Suite().test_a_memory_is_found_by_its_words_whatever_the_accents()


@pytest.fixture
def memories() -> Memories:
    return Memories(Journal(MemoryEventLog()), InMemoryMemoryStore())


async def test_every_change_is_logged(memories: Memories) -> None:
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
    assert await memories.recall("Mathilde", vector=None) == []


async def test_every_change_is_logged_before_it_applies() -> None:
    class FullDisk(MemoryEventLog):
        full = False

        async def append(self, event: Event) -> int:
            if self.full:
                raise ProviderError("disk", "full", transient=False)
            return await super().append(event)

    log, store = FullDisk(), InMemoryMemoryStore()
    memories = Memories(Journal(log), store)
    kept = await memories.remember("Mathilde est végétarienne")
    log.full = True

    for change in (
        memories.remember("Le chat s'appelle Biscotte"),
        memories.correct(kept.id, "Mathilde est végane"),
        memories.forget(kept.id),
    ):
        with pytest.raises(ProviderError):
            await change
    assert list(store.memories.values()) == [kept]


async def test_unknown_or_empty_memories_are_refused(memories: Memories) -> None:
    with pytest.raises(ContractError, match="needs some text"):
        await memories.remember("   ")
    with pytest.raises(ContractError, match="no memory"):
        await memories.forget("nope")


def agent(journal: Journal, tools: MemoryTools, model: ScriptedModel) -> Agent:
    return Agent(
        attachments=Attachments(MemoryBlobStore()),
        models=ModelChoice.single(model),
        persona=Persona(name="Richie", character="Tu es Richie."),
        journal=journal,
        household=HOUSEHOLD,
        localizer=EchoLocalizer(),
        toolbox=Toolbox(journal, providers=[tools]),
        context=[tools],
    )


def memory_tools(memories: Memories, journal: Journal, recall: RecallSettings | None = None) -> MemoryTools:
    """The memory tools of the test household, its episodes in memory."""
    episodes = Episodes(journal, InMemoryEpisodeStore())
    return MemoryTools(memories, episodes, HOUSEHOLD, journal, assistant="Richie", recall=recall)


async def test_a_fact_told_by_voice_is_known_later_on_telegram() -> None:
    journal = Journal(MemoryEventLog())
    tools = memory_tools(Memories(journal, InMemoryMemoryStore()), journal)
    remember = ToolCall("c1", "remember", {"text": "Mathilde est végétarienne", "about": "mathilde"})
    told = agent(journal, tools, ScriptedModel(remember, "C'est noté."))
    await told.respond(
        InboundMessage(address=VOICE, sender=Sender("mic"), text="Retiens que Mathilde est végétarienne")
    ).collect()

    model = ScriptedModel("Une poêlée de légumes, sans viande pour Mathilde.")
    later = agent(journal, tools, model)
    said = "Je cuisine quoi ce soir ?"  # no word in common: every memory is there while the budget allows
    await later.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text=said)).collect()

    assert "(about Mathilde) Mathilde est végétarienne" in model.requests[0].messages[0].text
    assert [m.content for m in model.requests[0].messages[1:]] == [said]


async def test_the_tools_recall_correct_and_forget_by_id() -> None:
    memories = Memories(Journal(MemoryEventLog()), InMemoryMemoryStore())
    tools = {t.name: t for t in memory_tools(memories, memories.journal).tools()}
    context = ToolContext(address=TELEGRAM, speaker=Speaker.account(MATHIS.id))

    def data(output: object) -> Mapping[str, object]:
        assert isinstance(output, Mapping)
        return output

    saved = data(
        await tools["remember"].run({"text": "Le portail s'ouvre avec le code 1234", "about": "household"}, context)
    )
    found = data(await tools["recall"].run({"query": "code du portail"}, context))
    today = f"{utc_now():%Y-%m-%d}"
    assert found["memories"] == [
        {"memory_id": saved["memory_id"], "text": f"{today} Le portail s'ouvre avec le code 1234"}
    ], "dated, so that the later of two memories that disagree is told apart"

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


async def test_beyond_its_budget_a_turn_adds_what_its_words_find_to_the_latest() -> None:
    memories = Memories(Journal(MemoryEventLog()), InMemoryMemoryStore())
    await memories.remember("Le portail s'ouvre avec le code 1234")
    await memories.remember("Mathilde est végétarienne", about=MATHILDE.id)
    tools = memory_tools(memories, memories.journal, recall=RecallSettings(recent=1))

    def turn(said: str | None) -> TurnContext:
        return TurnContext(person=MATHIS, speaker=Speaker.account(MATHIS.id), address=TELEGRAM, said=said)

    greeted = await tools.context(turn("Bonjour"))
    assert "végétarienne" in greeted[Layer.HOUSEHOLD] and "1234" not in greeted[Layer.HOUSEHOLD], "the latest"
    asked = await tools.context(turn("Quel code pour le portail ?"))
    assert "1234" in asked[Layer.TURN] and "végétarienne" not in asked[Layer.TURN], "found, without what is shown"
    assert Layer.TURN not in await tools.context(turn(None))

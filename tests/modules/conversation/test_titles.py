"""Each conversation of a channel whose conversations are listed is titled once, from its first exchange; a model
that fails leaves it untitled, and lists fall back to its first words."""

import asyncio

from nestor.core import ProviderError
from nestor.modules.channels import Address, Exchange, Medium
from nestor.modules.conversation import AssistantTurn, ConversationTitled, ConversationTitles, UserTurn
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal
from nestor.testing.cognition.model import ScriptedModel
from nestor.testing.journal import MemoryEventLog

TELEGRAM = Address("telegram", "42")


async def exchange(journal: Journal, conversation: str, said: str, answered: str) -> None:
    turn = Exchange(conversation_id=conversation, turn_id=f"{conversation}-{said}")
    session = TELEGRAM.session
    await journal.publish(
        UserTurn(
            source="test",
            session=session,
            address=TELEGRAM,
            text=said,
            exchange=turn,
            medium=Medium.WRITTEN,
            speaker=Speaker.unknown(),
        )
    )
    await journal.publish(AssistantTurn(source="test", session=session, address=TELEGRAM, text=answered, exchange=turn))


async def titles_of(journal: Journal, count: int) -> list[ConversationTitled]:
    for _ in range(100):
        if len(found := await journal.history(ConversationTitled)) >= count:
            return found
        await asyncio.sleep(0.01)
    return await journal.history(ConversationTitled)


async def test_a_conversation_is_titled_once_from_its_first_exchange() -> None:
    journal = Journal(MemoryEventLog())
    model = ScriptedModel('"Allumer le salon."', "Autre chose")
    titles = ConversationTitles(journal, model, ["telegram"], assistant="Richie", language="French")
    async with titles:
        await exchange(journal, "c1", "Allume le salon", "C'est fait.")
        await exchange(journal, "c1", "Et la cuisine ?", "Aussi.")
        (titled,) = await titles_of(journal, 1)
        await asyncio.sleep(0.05)
    assert (titled.conversation_id, titled.title, titled.session) == ("c1", "Allumer le salon", TELEGRAM.session)
    assert len(model.requests) == 1, "the next answers of the conversation are not titled again"
    assert "Allume le salon" in str(model.requests[0].messages[1].content)
    assert await journal.history(ConversationTitled) == [titled]


async def test_a_model_that_fails_leaves_the_conversation_untitled_and_the_next_ones_go_on() -> None:
    def down(request: object) -> str:
        raise ProviderError("scripted", "down", transient=True)

    journal = Journal(MemoryEventLog())
    async with ConversationTitles(journal, ScriptedModel(down, "Météo de demain"), ["telegram"], assistant="Richie"):
        await exchange(journal, "c1", "Bonjour", "Bonjour !")
        await asyncio.sleep(0.05)
        assert await journal.history(ConversationTitled) == []
        await exchange(journal, "c2", "Il fera beau ?", "Oui.")
        (titled,) = await titles_of(journal, 1)
    assert titled.conversation_id == "c2"


async def test_the_conversations_of_a_channel_nobody_lists_cost_no_title() -> None:
    journal = Journal(MemoryEventLog())
    model = ScriptedModel("Allumer le salon")
    async with ConversationTitles(journal, model, ["web"], assistant="Richie"):
        await exchange(journal, "c1", "Allume le salon", "C'est fait.")
        await asyncio.sleep(0.05)
    assert model.requests == [] and await journal.history(ConversationTitled) == []

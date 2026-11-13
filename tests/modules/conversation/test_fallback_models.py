"""A model that fails before answering hands the turn to its fallback, and the journal says so; one that fails once it
has started speaking does not, since a second answer would repeat the first's beginning."""

from collections.abc import AsyncGenerator

from nestor.core import ProviderError
from nestor.modules.channels import InboundMessage, Sender
from nestor.modules.cognition import (
    Document,
    FallingBack,
    Image,
    LanguageModel,
    Message,
    ModelFellBack,
    ModelOutput,
    ModelRequest,
    Role,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from nestor.modules.conversation import FallbackReason, FallbackSpoken, ModelChoice
from nestor.modules.journal import Journal
from nestor.testing.cognition import LanguageModelContract, ScriptedModel
from nestor.testing.journal import MemoryEventLog

from .conftest import TELEGRAM, MakeAgent

OVERLOADED = ProviderError("anthropic", "HTTP 529: Overloaded", transient=True)


def asked(text: str) -> InboundMessage:
    return InboundMessage(address=TELEGRAM, sender=Sender("42"), text=text)


class BreaksMidway(LanguageModel):
    """Starts an answer, then its provider fails."""

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        yield TextDelta("Il fait")
        raise OVERLOADED


async def test_when_a_model_fails_its_fallback_answers_and_the_journal_says_which(
    make_agent: MakeAgent, journal: Journal
) -> None:
    down, backup = ScriptedModel(fail=OVERLOADED), ScriptedModel("Il fait beau.")
    agent = make_agent(models=ModelChoice.single(FallingBack([("sonnet", down), ("gemini", backup)], journal)))

    assert await agent.respond(asked("Quel temps fait-il ?")).collect() == ("Il fait beau.",)

    [fell] = await journal.history(ModelFellBack)
    assert (fell.model, fell.fallback, fell.transient) == ("sonnet", "gemini", True)
    assert "Overloaded" in fell.error
    assert down.requests[0] == backup.requests[0], "the fallback is asked exactly what the model was"
    assert await journal.history(FallbackSpoken) == []


async def test_a_chain_where_every_model_fails_ends_in_the_usual_apology(
    make_agent: MakeAgent, journal: Journal
) -> None:
    chain = [("sonnet", ScriptedModel(fail=OVERLOADED)), ("gemini", ScriptedModel(fail=OVERLOADED))]
    agent = make_agent(models=ModelChoice.single(FallingBack(chain, journal)))

    await agent.respond(asked("Quel temps fait-il ?")).collect()

    assert [(e.model, e.fallback) for e in await journal.history(ModelFellBack)] == [("sonnet", "gemini")]
    [spoken] = await journal.history(FallbackSpoken)
    assert spoken.reason is FallbackReason.MODEL_UNAVAILABLE


async def test_a_model_that_fails_once_it_has_spoken_is_not_replaced(make_agent: MakeAgent, journal: Journal) -> None:
    backup = ScriptedModel("Il fait beau.")
    agent = make_agent(
        models=ModelChoice.single(FallingBack([("sonnet", BreaksMidway()), ("gemini", backup)], journal))
    )

    await agent.respond(asked("Quel temps fait-il ?")).collect()

    assert backup.requests == []
    assert await journal.history(ModelFellBack) == []
    assert len(await journal.history(FallbackSpoken)) == 1


class Reading(ScriptedModel):
    vision = True
    reads = frozenset({"application/pdf"})


async def test_a_fallback_gets_only_the_files_it_can_take(journal: Journal) -> None:
    blind = ScriptedModel("Je ne vois pas la photo.")
    falling = FallingBack([("claude", Reading(fail=OVERLOADED)), ("local", blind)], journal)
    seen = Message.user(
        "regarde",
        images=(Image(media_type="image/png", data=b"png"),),
        documents=(Document(media_type="application/pdf", data=b"%PDF"),),
    )
    [o async for o in falling.stream(ModelRequest(messages=(Message(role=Role.SYSTEM, content="Nestor"), seen)))]

    [_, sent] = blind.requests[0].messages
    assert (sent.content, sent.images, sent.documents) == ("regarde", (), ())


def light(request: ModelRequest) -> str | ToolCall:
    return ToolCall("c1", "set_light", {"room": "salon"}) if request.tools else "Ça va."


class TestFallingBack(LanguageModelContract):
    """A chain whose first model is down is a language model like any other."""

    def model(self) -> LanguageModel:
        chain = [("down", ScriptedModel(fail=OVERLOADED)), ("up", ScriptedModel(light))]
        return FallingBack(chain, Journal(MemoryEventLog()))

    def tool_request(self) -> ModelRequest:
        return ModelRequest(messages=(Message.user("Allume le salon."),), tools=(ToolSpec("set_light", "Lampe."),))

    def unavailable_model(self) -> LanguageModel:
        chain = [("a", ScriptedModel(fail=OVERLOADED)), ("b", ScriptedModel(fail=OVERLOADED))]
        return FallingBack(chain, Journal(MemoryEventLog()))

"""The central agent: answers, tools, fallbacks, interruptions and history, with doubles only."""

import asyncio
import json
from collections.abc import AsyncGenerator, Mapping

import pytest

from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.channels import Address, Sender
from nestor.modules.cognition.model import ModelOutput, ModelRequest, Role, TextDelta, ToolCall, ToolSpec
from nestor.modules.cognition.tools import Tool, ToolCalled, ToolCompleted, ToolContext, ToolFailed
from nestor.modules.conversation import (
    AgentSettings,
    AnswerCut,
    AssistantTurn,
    ContextProvider,
    FallbackReason,
    FallbackSpoken,
    UserTurn,
)
from nestor.modules.household import Person
from nestor.modules.journal import Journal
from nestor.testing.cognition.model import ScriptedModel

from .conftest import MATHIS, TELEGRAM, VOICE, MakeAgent, message


def tool(name: str, run, **kwargs) -> Tool:
    return Tool(spec=ToolSpec(name, f"{name} tool", {"type": "object", "properties": {}, **kwargs}), run=run)


async def test_an_answer_is_streamed_and_both_turns_are_logged(make_agent: MakeAgent, journal: Journal) -> None:
    agent = make_agent("Bonjour Mathis, tout va bien.")

    answer = await agent.respond(message("Salut")).collect()

    assert answer == "Bonjour Mathis, tout va bien."
    user, assistant = await journal.history(UserTurn), await journal.history(AssistantTurn)
    assert (user[0].text, user[0].person, user[0].session) == ("Salut", "mathis", TELEGRAM.session)
    assert (assistant[0].text, assistant[0].interrupted) == (answer, False)


def test_strangers_are_not_identified(make_agent: MakeAgent) -> None:
    agent = make_agent()
    assert agent.identify(TELEGRAM, Sender("42")) == "mathis"
    assert agent.identify(TELEGRAM, Sender("666")) is None


async def test_the_conversation_survives_a_restart(make_agent: MakeAgent) -> None:
    await make_agent("Noté, ton chat s'appelle Biscotte.").respond(message("Mon chat s'appelle Biscotte")).collect()
    model = ScriptedModel("Biscotte.")
    await make_agent(model=model).respond(message("Comment s'appelle mon chat ?")).collect()

    seen = [(m.role, m.content) for m in model.requests[0].messages[1:]]
    assert seen == [
        (Role.USER, "Mon chat s'appelle Biscotte"),
        (Role.ASSISTANT, "Noté, ton chat s'appelle Biscotte."),
        (Role.USER, "Comment s'appelle mon chat ?"),
    ]


async def test_conversations_do_not_share_their_history(make_agent: MakeAgent) -> None:
    await make_agent("Ok.").respond(message("Secret de Telegram")).collect()
    model = ScriptedModel("Oui ?")
    await make_agent(model=model).respond(message("Salut", VOICE, "mic")).collect()
    assert [m.content for m in model.requests[0].messages[1:]] == ["Salut"]


async def test_the_agent_calls_tools_and_answers_with_their_result(make_agent: MakeAgent, journal: Journal) -> None:
    contexts: list[ToolContext] = []

    async def light(arguments: Mapping[str, object], context: ToolContext) -> dict[str, object]:
        contexts.append(context)
        return {"room": arguments["room"], "state": "on"}

    def answer(request: ModelRequest) -> str:
        result = json.loads(request.messages[-1].content)
        return f"C'est allumé dans le {result['room']}."

    agent = make_agent(ToolCall("c1", "light_on", {"room": "salon"}), answer, tools=[tool("light_on", light)])

    assert await agent.respond(message("Allume le salon")).collect() == "C'est allumé dans le salon."
    assert contexts == [ToolContext(address=TELEGRAM, person=PersonId("mathis"))]
    called, completed = (await journal.history(ToolCalled))[0], (await journal.history(ToolCompleted))[0]
    assert (called.name, called.arguments, called.person) == ("light_on", {"room": "salon"}, "mathis")
    assert completed.ok and json.loads(completed.output) == {"room": "salon", "state": "on"}


async def test_a_tool_round_is_part_of_the_history(make_agent: MakeAgent) -> None:
    async def light(arguments: Mapping[str, object], context: ToolContext) -> str:
        return "allumée"

    await (
        make_agent(ToolCall("c1", "light_on"), "Fait.", tools=[tool("light_on", light)])
        .respond(message("Allume"))
        .collect()
    )
    model = ScriptedModel("Oui.")
    await make_agent(model=model, tools=[tool("light_on", light)]).respond(message("C'est fait ?")).collect()

    roles = [m.role for m in model.requests[0].messages[1:]]
    assert roles == [Role.USER, Role.ASSISTANT, Role.TOOL, Role.ASSISTANT, Role.USER]


async def test_a_failing_tool_is_reported_to_the_model_not_raised(make_agent: MakeAgent, journal: Journal) -> None:
    async def broken(arguments: Mapping[str, object], context: ToolContext) -> str:
        raise ToolFailed("la box Home Assistant ne répond pas")

    async def crashing(arguments: Mapping[str, object], context: ToolContext) -> str:
        raise RuntimeError("bug")

    model = ScriptedModel(
        ToolCall("c1", "light_on"),
        ToolCall("c2", "crash"),
        ToolCall("c3", "nope"),
        ToolCall("c4", "needs_room"),
        "Désolé, je n'y arrive pas.",
    )
    agent = make_agent(
        model=model,
        tools=[tool("light_on", broken), tool("crash", crashing), tool("needs_room", broken, required=["room"])],
    )

    assert await agent.respond(message("Allume")).collect() == "Désolé, je n'y arrive pas."
    errors = [json.loads(e.output)["error"] for e in await journal.history(ToolCompleted)]
    assert errors == [
        "la box Home Assistant ne répond pas",
        "crash failed (RuntimeError)",
        "unknown tool 'nope'",
        "missing arguments: room",
    ]


async def test_a_tool_that_hangs_times_out(make_agent: MakeAgent, journal: Journal) -> None:
    async def hangs(arguments: Mapping[str, object], context: ToolContext) -> str:
        await asyncio.sleep(10)
        return "trop tard"

    slow = Tool(spec=ToolSpec("slow", "slow"), run=hangs, timeout_s=0.01)
    await make_agent(ToolCall("c1", "slow"), "Ça ne répond pas.", tools=[slow]).respond(message("Vas-y")).collect()

    assert "did not answer" in (await journal.history(ToolCompleted))[0].output


async def test_a_model_stuck_calling_tools_is_stopped(make_agent: MakeAgent) -> None:
    async def noop(arguments: Mapping[str, object], context: ToolContext) -> str:
        return "ok"

    model = ScriptedModel(*[ToolCall(f"c{i}", "noop") for i in range(10)])
    agent = make_agent(model=model, tools=[tool("noop", noop)], settings=AgentSettings(max_tool_rounds=3))

    await agent.respond(message("Boucle")).collect()
    assert len(model.requests) == 3


async def test_an_unavailable_model_is_excused_aloud_and_logged(make_agent: MakeAgent, journal: Journal) -> None:
    agent = make_agent(model=ScriptedModel(fail=ProviderError("openrouter", "503", transient=True)))

    answer = await agent.respond(message("Salut", VOICE, "mic")).collect()

    assert answer == "Désolé, j'ai un trou de connexion. Tu peux répéter ?"
    assert [e.reason for e in await journal.history(FallbackSpoken)] == [FallbackReason.MODEL_UNAVAILABLE]


async def test_a_model_failing_midway_keeps_what_was_said_and_excuses_the_cut(
    make_agent: MakeAgent, journal: Journal
) -> None:
    class Dropping(ScriptedModel):
        async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
            yield TextDelta("Alors, la météo")
            raise ProviderError("openrouter", "connection reset", transient=True)

    answer = await make_agent(model=Dropping()).respond(message("Météo ?")).collect()

    assert answer == "Alors, la météo Désolé, j'ai un trou de connexion. Tu peux répéter ?"
    assert (await journal.history(AssistantTurn))[0].text == answer


async def test_a_reply_can_only_be_read_once(make_agent: MakeAgent) -> None:
    reply = make_agent("Une fois.").respond(message("Salut"))
    await reply.collect()
    with pytest.raises(ContractError, match="only be read once"):
        await reply.collect()


def test_two_tools_cannot_share_a_name(make_agent: MakeAgent) -> None:
    async def noop(arguments: Mapping[str, object], context: ToolContext) -> str:
        return ""

    with pytest.raises(ContractError, match="two tools are named"):
        make_agent(tools=[tool("same", noop), tool("same", noop)])


async def test_a_slow_model_gets_a_filler_on_voice_only(make_agent: MakeAgent, journal: Journal) -> None:
    settings = AgentSettings(slow_after_s=0.02)
    spoken = (
        await make_agent(model=ScriptedModel("Voilà.", word_delay_s=0.05), settings=settings)
        .respond(message("Question", VOICE, "mic"))
        .collect()
    )
    written = (
        await make_agent(model=ScriptedModel("Voilà.", word_delay_s=0.05), settings=settings)
        .respond(message("Question"))
        .collect()
    )

    assert spoken == "Hmm, je rame un peu, laisse-moi une seconde.Voilà."
    assert written == "Voilà."
    assert [e.reason for e in await journal.history(FallbackSpoken)] == [FallbackReason.MODEL_SLOW]


async def test_an_interruption_keeps_only_what_was_heard(make_agent: MakeAgent, journal: Journal) -> None:
    model = ScriptedModel("Il était une fois un très long conte sans fin", word_delay_s=0.01)
    reply = make_agent(model=model).respond(message("Raconte", VOICE, "mic"))

    chunks = []
    async for chunk in reply:
        chunks.append(chunk)
        if len(chunks) == 3:
            await reply.interrupt("Il était une")

    assert (await journal.history(AssistantTurn))[0].text == "Il était une"
    assert (await journal.history(AssistantTurn))[0].interrupted
    assert model.interrupted == 1


async def test_a_cut_after_the_answer_was_written_rewrites_the_history(make_agent: MakeAgent, journal: Journal) -> None:
    reply = make_agent("Une réponse entièrement écrite mais pas encore jouée.").respond(message("Dis", VOICE, "mic"))
    await reply.collect()
    await reply.interrupt("Une réponse")
    await reply.interrupt("ignoré : déjà coupé")

    model = ScriptedModel("D'accord.")
    await make_agent(model=model).respond(message("Stop", VOICE, "mic")).collect()

    assert len(await journal.history(AnswerCut)) == 1
    assert [m.content for m in model.requests[0].messages[1:]] == ["Dis", "Une réponse", "Stop"]


async def test_a_composed_message_uses_the_conversation_and_is_left_to_its_sender(
    make_agent: MakeAgent, journal: Journal
) -> None:
    await make_agent("Je lance l'analyse.").respond(message("Analyse le dépôt")).collect()
    model = ScriptedModel("L'analyse est finie : trois soucis trouvés.")

    text = await make_agent(model=model).compose(TELEGRAM, MATHIS, "Task finished: 3 issues found.")

    assert text == "L'analyse est finie : trois soucis trouvés."
    last = model.requests[0].messages[-1]
    assert (last.role, last.content) == (Role.SYSTEM, "Task finished: 3 issues found.")
    assert [t.text for t in await journal.history(UserTurn)] == ["Analyse le dépôt"]
    assert [t.text for t in await journal.history(AssistantTurn)] == ["Je lance l'analyse."]


async def test_an_answer_to_a_delivery_sees_the_delivery(make_agent: MakeAgent, journal: Journal) -> None:
    await journal.publish(
        AssistantTurn(source="courier", session=TELEGRAM.session, address=TELEGRAM, text="Ton analyse est prête.")
    )
    model = ScriptedModel("Rien d'autre.")
    await make_agent(model=model).respond(message("Rien d'autre ?")).collect()

    assert [m.role for m in model.requests[0].messages[1:]] == [Role.ASSISTANT, Role.USER]


async def test_instructions_carry_persona_channel_person_and_context(make_agent: MakeAgent) -> None:
    class Tasks(ContextProvider):
        async def context(self, person: Person | None, address: Address) -> str | None:
            return "Running tasks: none." if person else None

    class Silent(ContextProvider):
        async def context(self, person: Person | None, address: Address) -> str | None:
            return None

    model = ScriptedModel("Oui.", "Oui.")
    agent = make_agent(model=model, context=[Tasks(), Silent()])
    await agent.respond(message("Salut", VOICE, "mic")).collect()
    await agent.respond(message("Salut", Address("web", "x"), "inconnu")).collect()

    spoken, written = (r.messages[0].content for r in model.requests)
    assert "Tu es Richie" in spoken and "Mathis" in spoken and "spoken aloud" in spoken
    assert "[laughs]" in spoken and "Running tasks: none." in spoken and "Europe/Paris" in spoken
    assert "do not know who" in written and "chat" in written and "Running tasks" not in written

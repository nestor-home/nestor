"""The central agent: answers, tools, fallbacks, interruptions and history, with doubles only."""

import asyncio
import json
from collections.abc import AsyncGenerator, Mapping

import pytest

from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.channels import Address, Medium, Sender
from nestor.modules.cognition.model import (
    Finished,
    FinishReason,
    ModelOutput,
    ModelRequest,
    Role,
    TextDelta,
    ToolCall,
    ToolCallRequested,
    ToolSpec,
)
from nestor.modules.cognition.tools import Tool, ToolCalled, ToolCompleted, ToolContext, ToolFailed
from nestor.modules.conversation import (
    AgentSettings,
    AnswerCut,
    AssistantTurn,
    ContextProvider,
    FallbackReason,
    FallbackSpoken,
    Layer,
    ModelChoice,
    Notification,
    NotificationTurn,
    Sections,
    TurnContext,
    UserTurn,
)
from nestor.modules.identity import Heard, Speaker
from nestor.modules.journal import Journal
from nestor.testing.cognition.model import ScriptedModel

from .conftest import MATHIS, TELEGRAM, VOICE, MakeAgent, message


def tool(name: str, run, **kwargs) -> Tool:
    return Tool(spec=ToolSpec(name, f"{name} tool", {"type": "object", "properties": {}, **kwargs}), run=run)


async def test_an_answer_is_streamed_and_both_turns_are_logged(make_agent: MakeAgent, journal: Journal) -> None:
    agent = make_agent("Bonjour Mathis, tout va bien.")

    (answer,) = await agent.respond(message("Salut")).collect()

    assert answer == "Bonjour Mathis, tout va bien."
    user, assistant = await journal.history(UserTurn), await journal.history(AssistantTurn)
    assert (user[0].text, user[0].person, user[0].session) == ("Salut", "mathis", TELEGRAM.session)
    assert (assistant[0].text, assistant[0].interrupted) == (answer, False)


async def test_each_medium_answers_with_its_own_model(make_agent: MakeAgent) -> None:
    spoken, written = ScriptedModel("Il fait beau.", "C'est prêt."), ScriptedModel("Voici le détail.", "Envoyé.")
    agent = make_agent(models=ModelChoice(spoken=spoken, written=written))

    said = await agent.respond(message("Quel temps ?", VOICE, "mic")).collect()
    typed = await agent.respond(message("Et en détail ?", VOICE, "mic", medium=Medium.WRITTEN)).collect()
    composed = await agent.compose(TELEGRAM, MATHIS, Notification("The parcel arrived.", "watch w1"), Medium.SPOKEN)

    assert (said, typed, composed) == (("Il fait beau.",), ("Voici le détail.",), ("C'est prêt.",))
    assert (len(spoken.requests), len(written.requests)) == (2, 1)


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

    assert await agent.respond(message("Allume le salon")).collect() == ("C'est allumé dans le salon.",)
    assert [(c.address, c.person) for c in contexts] == [(TELEGRAM, PersonId("mathis"))]
    called, completed = (await journal.history(ToolCalled))[0], (await journal.history(ToolCompleted))[0]
    assert (called.name, called.arguments, called.person) == ("light_on", {"room": "salon"}, "mathis")
    assert completed.ok and json.loads(completed.output) == {"room": "salon", "state": "on"}


class Announcing(ScriptedModel):
    """Says a sentence, then calls a tool in the same round (what real models do), then answers."""

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        self.requests.append(request)
        if len(self.requests) == 1:
            yield TextDelta("Je regarde")
            yield TextDelta(".")
            yield ToolCallRequested(ToolCall("c1", "light_on"))
            yield Finished(FinishReason.TOOL_CALLS)
        else:
            yield TextDelta("C'est allumé.")
            yield Finished(FinishReason.STOP)


async def light_on(arguments: Mapping[str, object], context: ToolContext) -> str:
    return "on"


async def test_text_before_a_tool_call_is_a_message_of_its_own_handed_over_before_the_tool_runs(
    make_agent: MakeAgent,
) -> None:
    first_read = asyncio.Event()

    async def light(arguments: Mapping[str, object], context: ToolContext) -> str:
        await first_read.wait()  # the tool cannot end before the first message is out
        return "on"

    messages = make_agent(model=Announcing(), tools=[tool("light_on", light)]).respond(message("Allume")).messages()

    assert await asyncio.wait_for(anext(messages), 1) == "Je regarde."
    first_read.set()
    assert [m async for m in messages] == ["C'est allumé."]


async def test_messages_are_logged_in_the_order_the_user_saw_them(make_agent: MakeAgent, journal: Journal) -> None:
    await make_agent(model=Announcing(), tools=[tool("light_on", light_on)]).respond(message("Allume")).collect()

    logged = await journal.history(UserTurn, AssistantTurn, ToolCalled, ToolCompleted)
    said = [e.text if isinstance(e, UserTurn | AssistantTurn) else type(e).__name__ for e in logged]
    assert said == ["Allume", "Je regarde.", "ToolCalled", "ToolCompleted", "C'est allumé."]

    model = ScriptedModel("Oui.")
    await make_agent(model=model, tools=[tool("light_on", light_on)]).respond(message("C'est fait ?")).collect()
    replayed = [(m.role, m.content, [c.name for c in m.tool_calls]) for m in model.requests[0].messages[1:]]
    assert replayed == [
        (Role.USER, "Allume", []),
        (Role.ASSISTANT, "Je regarde.", ["light_on"]),  # as the model wrote it: the sentence with its call
        (Role.TOOL, "on", []),
        (Role.ASSISTANT, "C'est allumé.", []),
        (Role.USER, "C'est fait ?", []),
    ]


async def test_a_tool_call_without_text_makes_no_empty_message(make_agent: MakeAgent, journal: Journal) -> None:
    agent = make_agent(ToolCall("c1", "light_on"), "C'est allumé.", tools=[tool("light_on", light_on)])

    assert await agent.respond(message("Allume")).collect() == ("C'est allumé.",)
    assert [t.text for t in await journal.history(AssistantTurn)] == ["C'est allumé."]


async def test_voice_speaks_the_messages_as_one_text(make_agent: MakeAgent) -> None:
    reply = make_agent(model=Announcing(), tools=[tool("light_on", light_on)]).respond(message("Allume", VOICE, "mic"))

    assert "".join([chunk async for chunk in reply.speech()]) == "Je regarde. C'est allumé."


async def test_a_cut_across_messages_keeps_what_was_heard_of_each(make_agent: MakeAgent, journal: Journal) -> None:
    reply = make_agent(model=Announcing(), tools=[tool("light_on", light_on)]).respond(message("Allume", VOICE, "mic"))
    await reply.collect()
    await reply.interrupt("Je regarde. C'est")  # word by word, as the synthesis reports them

    [_, second] = await journal.history(AssistantTurn)
    [cut] = await journal.history(AnswerCut)
    assert (cut.answer, cut.heard) == (second.id, "C'est")
    model = ScriptedModel("Pardon.")
    await make_agent(model=model, tools=[tool("light_on", light_on)]).respond(message("Hein ?", VOICE, "mic")).collect()
    assert [m.content for m in model.requests[0].messages[1:] if m.role is Role.ASSISTANT] == ["Je regarde.", "C'est"]


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

    assert await agent.respond(message("Allume")).collect() == ("Désolé, je n'y arrive pas.",)
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

    assert answer == ("Désolé, j'ai un trou de connexion. Tu peux répéter ?",)
    assert [e.reason for e in await journal.history(FallbackSpoken)] == [FallbackReason.MODEL_UNAVAILABLE]


async def test_a_model_failing_midway_keeps_what_was_said_and_excuses_the_cut(
    make_agent: MakeAgent, journal: Journal
) -> None:
    class Dropping(ScriptedModel):
        async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
            yield TextDelta("Alors, la météo")
            raise ProviderError("openrouter", "connection reset", transient=True)

    (answer,) = await make_agent(model=Dropping()).respond(message("Météo ?")).collect()

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
    typed_on_voice = (
        await make_agent(model=ScriptedModel("Voilà.", word_delay_s=0.05), settings=settings)
        .respond(message("Question", VOICE, "mic", Medium.WRITTEN))
        .collect()
    )

    assert spoken == ("Hmm, je rame un peu, laisse-moi une seconde. Voilà.",)
    assert written == typed_on_voice == ("Voilà.",)
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

    notification = Notification("Task finished: 3 issues found.", "task t1 completed")
    text = await make_agent(model=model).compose(TELEGRAM, MATHIS, notification, Medium.WRITTEN)

    assert text == ("L'analyse est finie : trois soucis trouvés.",)
    last = model.requests[0].messages[-1]
    assert last.role is Role.USER and last.content.endswith("Task finished: 3 issues found.")
    assert "not said by anyone here: task t1 completed" in last.content, "never taken for the person's words"
    assert await journal.history(NotificationTurn) == [], "a draft: nothing is said before it is delivered"
    assert [t.text for t in await journal.history(AssistantTurn)] == ["Je lance l'analyse."]


async def test_an_answer_to_a_delivery_sees_what_it_was_about(make_agent: MakeAgent, journal: Journal) -> None:
    """A task's result comes back as a tool's result does: the notification, then the message it caused, then the
    person's question about it, all in one history the model can quote from."""
    model = ScriptedModel("Le deuxième : la CI est rouge sur main.")
    agent = make_agent(model=model)
    notification = Notification("Result: 1. tests flaky 2. CI red on main 3. lockfile stale", "task t1 completed")
    exchange = await agent.delivered(
        TELEGRAM, MATHIS, notification, Medium.WRITTEN, ["Ton analyse est prête : trois soucis."]
    )
    await agent.respond(message("Et le deuxième point ?")).collect()

    history = model.requests[0].messages[1:]
    assert [m.role for m in history] == [Role.USER, Role.ASSISTANT, Role.USER]
    assert "CI red on main" in history[0].content and history[2].content == "Et le deuxième point ?"
    [internal] = await journal.history(NotificationTurn)
    [said] = [t for t in await journal.history(AssistantTurn) if t.exchange == exchange]
    assert internal.exchange == exchange and internal.person == MATHIS.id and said.text.startswith("Ton analyse")
    assert [t.speaker for t in await journal.history(UserTurn)] == [Speaker.account(MATHIS.id)]


async def test_instructions_carry_persona_channel_person_and_context(make_agent: MakeAgent) -> None:
    class Tasks(ContextProvider):
        async def context(self, turn: TurnContext) -> Sections:
            return {Layer.TURN: "Running tasks: none."} if turn.person else {}

    class Silent(ContextProvider):
        async def context(self, turn: TurnContext) -> Sections:
            return {}

    model = ScriptedModel("Oui.", "Oui.")
    agent = make_agent(model=model, context=[Tasks(), Silent()])
    mathis = Heard(space="s", voiceprint=(1.0,), duration_s=2.0, person=MATHIS.id, score=0.9, margin=0.9)
    await agent.respond(message("Salut", VOICE, heard=mathis)).collect()
    await agent.respond(message("Salut", Address("web", "x"), "inconnu")).collect()

    spoken, written = (r.messages[0].text for r in model.requests)
    assert "Tu es Richie" in spoken and "Mathis, recognised by their voice" in spoken and "spoken aloud" in spoken
    assert "[laughs]" in spoken and "Running tasks: none." in spoken and "Europe/Paris" in spoken
    assert "do not know who" in written and "chat" in written and "Running tasks" not in written


async def test_modules_look_things_up_with_the_last_words_of_the_conversation(make_agent: MakeAgent) -> None:
    looked_up: list[str | None] = []

    class Lookup(ContextProvider):
        async def context(self, turn: TurnContext) -> Sections:
            looked_up.append(turn.said)
            return {}

    agent = make_agent("Des pâtes.", "Sans gluten, alors.", context=[Lookup()])
    await agent.respond(message("Je cuisine quoi pour Mathilde ?")).collect()
    await agent.respond(message("Et elle mange du gluten ?")).collect()
    assert looked_up == [
        "Je cuisine quoi pour Mathilde ?",
        "Je cuisine quoi pour Mathilde ? Et elle mange du gluten ?",
    ], "a follow-up keeps its subject"


async def test_the_instructions_run_from_what_never_changes_to_what_this_turn_brings(make_agent: MakeAgent) -> None:
    class Book(ContextProvider):
        def guidance(self) -> str:
            return "Use the book tools."

        async def context(self, turn: TurnContext) -> Sections:
            return {Layer.HOUSEHOLD: "Books lent: Tintin."}

    class Tasks(ContextProvider):
        async def context(self, turn: TurnContext) -> Sections:
            return {Layer.TURN: f"Tasks for {turn.person.name if turn.person else 'nobody'}: none."}

    model = ScriptedModel("Oui.", "Oui.")
    agent = make_agent(model=model, context=[Book(), Tasks()])
    await agent.respond(message("Salut")).collect()
    await agent.respond(message("Salut", Address("telegram", "666"), "666")).collect()

    (stable, household), (again, same) = (r.messages[0].layers for r in model.requests)
    first, second = (r.messages[0].content for r in model.requests)
    assert (stable, household) == (again, same), "who speaks and when only change the last part"
    assert "Tu es Richie" in stable and "Use the book tools." in stable and "Books lent" not in stable
    assert household == "The household: Mathis.\n\nBooks lent: Tintin."
    assert "Now:" in first and "talking with Mathis" in first and "Tasks for Mathis: none." in first
    assert "do not know who" in second and "Tasks for nobody: none." in second


async def test_a_cut_is_shared_by_length_whatever_the_synthesis_made_of_the_words(
    make_agent: MakeAgent, journal: Journal
) -> None:
    class Laughing(Announcing):
        async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
            async for output in super().stream(request):
                yield TextDelta("[laughs softly] Je regarde") if output == TextDelta("Je regarde") else output

    reply = make_agent(model=Laughing(), tools=[tool("light_on", light_on)]).respond(message("Allume", VOICE, "mic"))
    await reply.collect()
    await reply.interrupt("[laughs soft ly] Je regarde. C'est")  # the tag cut in three

    [_, second] = await journal.history(AssistantTurn)
    [cut] = await journal.history(AnswerCut)
    assert (cut.answer, cut.heard) == (second.id, "C'est")


async def test_two_messages_sent_together_are_answered_one_after_the_other(make_agent: MakeAgent) -> None:
    """One turn at a time per conversation: the second message is answered knowing the first answer."""
    model = ScriptedModel("Il fait vingt degrés.", "Oui, au salon.", word_delay_s=0.01)
    agent = make_agent(model=model)

    first, second = await asyncio.gather(
        agent.respond(message("Quelle température ?")).collect(), agent.respond(message("Au salon ?")).collect()
    )

    assert (first, second) == (("Il fait vingt degrés.",), ("Oui, au salon.",))
    assert [m.content for m in model.requests[1].messages[1:]] == [
        "Quelle température ?",
        "Il fait vingt degrés.",
        "Au salon ?",
    ]


async def test_an_interrupted_turn_frees_the_conversation_for_the_next(make_agent: MakeAgent) -> None:
    agent = make_agent(model=ScriptedModel("Alors voilà une très longue histoire", "D'accord.", word_delay_s=0.05))
    talking = agent.respond(message("Raconte", VOICE))
    stream = aiter(talking)
    await anext(stream)
    await talking.interrupt("Alors")

    assert await asyncio.wait_for(agent.respond(message("Stop", VOICE)).collect(), 1) == ("D'accord.",)

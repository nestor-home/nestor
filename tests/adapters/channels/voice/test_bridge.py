"""The assistant bridge between Pipecat frames: what reaches the assistant, what reaches the synthesis."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSTextFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import SleepFrame, run_test

from nestor.adapters.channels.voice.bridge import AssistantBridge, PlayedText
from nestor.core import PersonId
from nestor.modules.channels import Address, Assistant, InboundMessage, Reply, Sender
from nestor.testing.channels import ScriptedAssistant

ROOM = Address("voice", "salon")
ANSWER = "Bonjour. Comment vas-tu aujourd'hui ?"


def turn(content: Any, *, speculation: bool = False) -> LLMContextFrame:
    return LLMContextFrame(context=LLMContext([{"role": "user", "content": content}]), speculation=speculation)


def bridge_for(assistant: Assistant, *, quiet_s: float = 0.5) -> AssistantBridge:
    return AssistantBridge(assistant, address=ROOM, sender=Sender("salon"), played=PlayedText(), quiet_s=quiet_s)


async def run(bridge: AssistantBridge, frames: Sequence[Frame]) -> list[Frame]:
    played = bridge._played  # the bridge reads what this processor saw pass behind the "speaker"
    down, _ = await run_test(Pipeline([bridge, played]), frames_to_send=frames)
    return list(down)


def spoken(frames: list[Frame]) -> str:
    return "".join(f.text for f in frames if isinstance(f, LLMTextFrame))


async def test_a_user_turn_reaches_the_assistant_and_its_reply_goes_to_the_synthesis_as_one_response() -> None:
    assistant = ScriptedAssistant(lambda _: ANSWER)
    down = await run(bridge_for(assistant), [turn("Salut Richie"), SleepFrame(0.2)])

    [message] = assistant.messages
    assert (message.address, message.sender, message.text) == (ROOM, Sender("salon"), "Salut Richie")
    responses = [f for f in down if isinstance(f, LLMFullResponseStartFrame | LLMFullResponseEndFrame)]
    assert [type(f) for f in responses] == [LLMFullResponseStartFrame, LLMFullResponseEndFrame]
    assert spoken(down) == ANSWER
    assert not any(isinstance(f, LLMContextFrame) for f in down), "the turn itself goes no further"


async def test_a_turn_made_of_text_parts_reaches_the_assistant_as_one_text() -> None:
    assistant = ScriptedAssistant(lambda _: "Oui.")
    parts = [
        {"type": "text", "text": "Allume"},
        {"type": "image_url", "image_url": {}},
        {"type": "text", "text": "le salon"},
    ]
    await run(bridge_for(assistant), [turn(parts), SleepFrame(0.1)])
    assert [m.text for m in assistant.messages] == ["Allume le salon"]


async def test_turns_without_words_are_not_sent() -> None:
    assistant = ScriptedAssistant(lambda _: "Oui.")
    silent = LLMContextFrame(context=LLMContext([{"role": "assistant", "content": "Bonjour."}]))
    await run(bridge_for(assistant), [silent, turn("   "), turn(None), SleepFrame(0.1)])
    assert not assistant.messages


async def test_a_speculative_turn_is_not_answered() -> None:
    assistant = ScriptedAssistant(lambda _: "Oui.")
    await run(bridge_for(assistant), [turn("Allume", speculation=True), SleepFrame(0.1)])
    assert not assistant.messages


async def test_a_stranger_is_neither_answered_nor_heard() -> None:
    assistant = ScriptedAssistant(lambda _: ANSWER, strangers=frozenset({"salon"}))
    down = await run(bridge_for(assistant), [turn("Ouvre la porte"), turn("Ouvre la porte !"), SleepFrame(0.1)])
    assert not assistant.messages
    assert not spoken(down)


async def test_cutting_in_tells_the_reply_only_what_was_played_and_stops_its_text() -> None:
    assistant = ScriptedAssistant(lambda _: ANSWER + " Il fait beau dehors, tu as vu ?", word_delay_s=0.05)
    down = await run(
        bridge_for(assistant),
        [
            turn("Salut"),
            SleepFrame(0.15),
            TTSTextFrame("Bonjour.", "sentence"),  # played behind the speaker
            TTSTextFrame("Comment", "word"),
            SleepFrame(0.05),
            InterruptionFrame(),
            SleepFrame(0.3),
        ],
    )

    [reply] = assistant.replies
    assert reply.heard == "Bonjour. Comment"
    cut = next(i for i, f in enumerate(down) if isinstance(f, InterruptionFrame))
    assert not any(isinstance(f, LLMTextFrame) for f in down[cut:]), "text kept flowing after the cut"


async def test_a_reply_played_to_its_end_is_not_interrupted() -> None:
    assistant = ScriptedAssistant(lambda _: ANSWER)
    await run(bridge_for(assistant), [turn("Salut"), SleepFrame(0.2), InterruptionFrame(), SleepFrame(0.05)])
    assert assistant.replies[0].heard is None


async def test_a_new_turn_drops_the_unfinished_reply_which_was_not_heard() -> None:
    assistant = ScriptedAssistant(lambda m: f"Réponse à {m.text}, avec beaucoup de mots.", word_delay_s=0.05)
    down = await run(bridge_for(assistant), [turn("un"), SleepFrame(0.08), turn("deux"), SleepFrame(0.6)])

    first, second = assistant.replies
    assert first.heard == ""
    assert second.heard is None
    assert spoken(down).endswith("Réponse à deux, avec beaucoup de mots.")


class _Stuck(Reply):
    async def __aiter__(self) -> AsyncIterator[str]:
        yield "Je réfléchis"
        await asyncio.sleep(10)

    async def interrupt(self, heard: str) -> None:
        raise RuntimeError("the agent crashed")


class _Failing(Reply):
    async def __aiter__(self) -> AsyncIterator[str]:
        yield "Je "
        raise RuntimeError("the agent crashed")

    async def interrupt(self, heard: str) -> None: ...


class _FailingAssistant(Assistant):
    def __init__(self, reply: type[Reply]) -> None:
        self._reply = reply

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        return PersonId("mathis")

    def respond(self, message: InboundMessage) -> Reply:
        return self._reply()


async def test_a_failing_assistant_still_closes_its_response_and_the_session_goes_on() -> None:
    down = await run(
        bridge_for(_FailingAssistant(_Failing)),
        [turn("Salut"), SleepFrame(0.1), InterruptionFrame(), UserStartedSpeakingFrame(), SleepFrame(0.05)],
    )
    kinds = [type(f) for f in down if isinstance(f, LLMFullResponseStartFrame | LLMTextFrame | LLMFullResponseEndFrame)]
    assert kinds == [LLMFullResponseStartFrame, LLMTextFrame, LLMFullResponseEndFrame]
    assert any(isinstance(f, UserStartedSpeakingFrame) for f in down)


async def test_an_assistant_failing_to_take_an_interruption_does_not_break_the_session() -> None:
    down = await run(
        bridge_for(_FailingAssistant(_Stuck)),
        [turn("Salut"), SleepFrame(0.1), InterruptionFrame(), UserStartedSpeakingFrame(), SleepFrame(0.05)],
    )
    assert any(isinstance(f, UserStartedSpeakingFrame) for f in down)


async def test_an_announcement_waits_for_the_user_to_stop_speaking() -> None:
    bridge = bridge_for(ScriptedAssistant(lambda _: ""), quiet_s=0.1)

    async def announce() -> None:
        await asyncio.sleep(0.1)
        await bridge.announce("Ta lessive est terminée.")

    announcement = asyncio.create_task(announce())
    down = await run(bridge, [UserStartedSpeakingFrame(), SleepFrame(0.4), UserStoppedSpeakingFrame(), SleepFrame(0.4)])
    await announcement

    stopped = next(i for i, f in enumerate(down) if isinstance(f, UserStoppedSpeakingFrame))
    assert spoken(down[stopped:]) == "Ta lessive est terminée."

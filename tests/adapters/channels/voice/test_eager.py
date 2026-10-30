import asyncio
from collections.abc import AsyncIterator

from pipecat.frames.frames import LLMContextFrame, LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import SleepFrame, run_test

from nestor.adapters.channels.voice.bridge import AssistantBridge, PlayedText
from nestor.adapters.channels.voice.eager import ResponseWatcher, SentenceFlushFrame
from nestor.core import PersonId
from nestor.modules.channels import Address, Assistant, InboundMessage, Reply, Sender

from .doubles import ToneTTS
from .replay import ScenarioClock


class _ThinkingAloud(Reply):
    """Says a short sentence, then goes quiet while it calls a tool."""

    async def __aiter__(self) -> AsyncIterator[str]:
        yield "Je regarde ça."
        await asyncio.sleep(1.0)
        yield " Il fait beau."

    async def interrupt(self, heard: str) -> None: ...


class _Assistant(Assistant):
    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        return PersonId("mathis")

    def respond(self, message: InboundMessage) -> Reply:
        return _ThinkingAloud()


async def test_the_first_sentence_is_not_held_back_while_the_assistant_calls_a_tool() -> None:
    clock = ScenarioClock()
    tts = ToneTTS(clock, ttfb_s=0.0, secs_per_char=0.001)
    played = PlayedText()
    bridge = AssistantBridge(_Assistant(), address=Address("voice", "salon"), sender=Sender("salon"), played=played)
    turn = LLMContextFrame(context=LLMContext([{"role": "user", "content": "Quel temps fait-il ?"}]))
    clock.start()
    await run_test(Pipeline([bridge, ResponseWatcher(), tts, played]), frames_to_send=[turn, SleepFrame(1.5)])

    (first_at, first), (_, second) = tts.spoken
    assert (first, second) == ("Je regarde ça.", "Il fait beau.")
    assert first_at < 0.5, f"the first sentence waited {first_at:.2f} s for the tool call"


async def test_a_flush_with_nothing_pending_says_nothing_more() -> None:
    clock = ScenarioClock()
    tts = ToneTTS(clock, ttfb_s=0.0, secs_per_char=0.001)
    clock.start()
    frames = [LLMFullResponseStartFrame(), LLMTextFrame("Bonjour."), SentenceFlushFrame(), SleepFrame(0.1)]
    await run_test(tts, frames_to_send=[*frames, SentenceFlushFrame(), LLMFullResponseEndFrame(), SleepFrame(0.1)])
    assert tts.texts == ["Bonjour."]

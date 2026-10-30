import asyncio

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)

from nestor.adapters.channels.voice.turns import BackchannelAwareStart, is_backchannel


@pytest.mark.parametrize(
    "text", ["Mmh.", "Ouais.", "D'accord, d'accord.", "Ah ouais ?", "ok", "Oui oui", "D\u2019accord"]
)
def test_acknowledgements_are_backchannels(text: str) -> None:
    assert is_backchannel(text)


@pytest.mark.parametrize(
    "text", ["Attends, stop.", "Non.", "Ok ça suffit, merci.", "Et les ours polaires ?", "Ouais mais non", "Excuse-moi"]
)
def test_anything_else_is_a_real_turn(text: str) -> None:
    assert not is_backchannel(text)


def test_nothing_heard_is_not_a_backchannel() -> None:
    assert not is_backchannel("")
    assert not is_backchannel(" ... ")


class Strategy:
    """A start strategy and what it decided."""

    def __init__(self, *, long_speech_s: float = 1.2) -> None:
        self.strategy = BackchannelAwareStart(long_speech_s=long_speech_s)
        self.turns = 0
        self.resets = 0
        self.strategy.add_event_handler("on_user_turn_started", self._started)
        self.strategy.add_event_handler("on_reset_aggregation", self._reset)

    async def feed(self, *frames: Frame) -> None:
        for frame in frames:
            await self.strategy.process_frame(frame)

    async def _started(self, *_: object) -> None:
        self.turns += 1

    async def _reset(self, *_: object) -> None:
        self.resets += 1


def _words(text: str) -> TranscriptionFrame:
    return TranscriptionFrame(text, "user", "2026-10-30T12:00:00")


async def test_while_the_assistant_is_silent_voice_activity_starts_the_turn_at_once() -> None:
    probe = Strategy()
    await probe.feed(VADUserStartedSpeakingFrame())
    assert probe.turns == 1


async def test_while_the_assistant_is_silent_words_start_the_turn_even_without_voice_activity() -> None:
    probe = Strategy()
    await probe.feed(InterimTranscriptionFrame("Mmh", "user", "2026-10-30T12:00:00"))
    assert probe.turns == 1


async def test_an_acknowledgement_over_the_assistant_is_ignored_and_forgotten() -> None:
    probe = Strategy()
    await probe.feed(
        BotStartedSpeakingFrame(),
        VADUserStartedSpeakingFrame(),
        InterimTranscriptionFrame("Mmh", "user", "2026-10-30T12:00:00"),
        _words("Mmh."),
        VADUserStoppedSpeakingFrame(),
    )
    assert (probe.turns, probe.resets) == (0, 1)


async def test_a_real_word_over_the_assistant_starts_the_turn() -> None:
    probe = Strategy()
    await probe.feed(BotStartedSpeakingFrame(), VADUserStartedSpeakingFrame(), _words("Attends"))
    assert probe.turns == 1


async def test_long_speech_over_the_assistant_starts_the_turn_even_without_words() -> None:
    probe = Strategy(long_speech_s=0.05)
    await probe.feed(BotStartedSpeakingFrame(), VADUserStartedSpeakingFrame())
    await asyncio.sleep(0.1)
    assert probe.turns == 1


async def test_short_speech_over_the_assistant_does_not_start_the_turn() -> None:
    probe = Strategy(long_speech_s=0.05)
    await probe.feed(BotStartedSpeakingFrame(), VADUserStartedSpeakingFrame(), VADUserStoppedSpeakingFrame())
    await asyncio.sleep(0.1)
    await probe.strategy.cleanup()
    assert probe.turns == 0


async def test_once_the_assistant_stopped_speaking_voice_activity_starts_the_turn_again() -> None:
    probe = Strategy()
    await probe.feed(BotStartedSpeakingFrame(), BotStoppedSpeakingFrame(), VADUserStartedSpeakingFrame())
    await probe.strategy.handle_user_turn_started()
    assert probe.turns == 1

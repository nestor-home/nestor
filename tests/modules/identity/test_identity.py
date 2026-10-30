"""Identity contracts, proven on tagged doubles; real models will run the same suites."""

import pytest

from nestor.core import PersonId
from nestor.modules.identity import Identification
from nestor.testing.identity import (
    DiarizerContract,
    SpeakerIdentifierContract,
    TaggedDiarizer,
    TaggedIdentifier,
    tagged,
)


class TestTaggedDiarizer(DiarizerContract):
    def diarizer(self) -> TaggedDiarizer:
        return TaggedDiarizer()

    def speech(self, speaker: str, seconds: float) -> bytes:
        return tagged(speaker, seconds)


class TestTaggedIdentifier(SpeakerIdentifierContract):
    def identifier(self) -> TaggedIdentifier:
        return TaggedIdentifier()

    def speech(self, speaker: str, seconds: float) -> bytes:
        return tagged(speaker, seconds)


async def test_the_identifier_contract_rejects_a_guesser() -> None:
    class Guesser(TaggedIdentifier):
        async def identify(self, audio: bytes) -> Identification:
            return Identification(PersonId("mathis"), 0.4)

    class Suite(SpeakerIdentifierContract):
        def identifier(self) -> Guesser:
            return Guesser()

        def speech(self, speaker: str, seconds: float) -> bytes:
            return tagged(speaker, seconds)

    with pytest.raises(AssertionError, match="nobody enrolled"):
        await Suite().test_an_enrolled_voice_is_recognised_and_a_stranger_is_not()


async def test_silence_between_turns_is_not_a_speaker() -> None:
    async def audio():
        yield tagged("a", 1.0)
        yield b"\0" * 32000
        yield tagged("a", 1.0)

    final = [s async for s in TaggedDiarizer().diarize(audio())][-1]
    assert [(s.start_s, s.end_s) for s in final] == [(0.0, 1.0), (2.0, 3.0)]

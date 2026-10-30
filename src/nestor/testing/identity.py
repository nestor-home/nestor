"""Doubles and contract suites for speaker identity.

The doubles treat audio as text-tagged bytes (`b"voice:mathis|..."`), so behaviour can be tested
without any model.
"""

import itertools
from collections.abc import AsyncIterable, AsyncIterator

from nestor.core import PersonId
from nestor.modules.identity import Diarizer, Identification, Segment, SpeakerIdentifier, SpeakerLabel


def tagged(speaker: str, seconds: float = 1.0, *, rate: int = 16000) -> bytes:
    """Fake speech: a speaker tag, padded to the byte length of `seconds` of 16-bit mono audio."""
    tag = f"voice:{speaker}|".encode()
    return tag + b"\0" * max(0, int(seconds * rate * 2) - len(tag))


def speaker_of(audio: bytes) -> str | None:
    if not audio.startswith(b"voice:"):
        return None
    return audio[6 : audio.index(b"|")].decode()


class TaggedDiarizer(Diarizer):
    """Labels each chunk by its tag, merging consecutive chunks of the same speaker."""

    name = "tagged-diarizer"

    async def diarize(self, audio: AsyncIterable[bytes]) -> AsyncIterator[list[Segment]]:
        labels: dict[str, SpeakerLabel] = {}
        segments: list[Segment] = []
        position = 0.0
        async for chunk in audio:
            duration = len(chunk) / (2 * self.sample_rate)
            voice = speaker_of(chunk)
            if voice is not None:
                label = labels.setdefault(voice, SpeakerLabel(f"spk-{len(labels)}"))
                if segments and segments[-1].speaker == label and segments[-1].end_s == position:
                    segments[-1] = Segment(segments[-1].start_s, position + duration, label)
                else:
                    segments.append(Segment(position, position + duration, label))
                yield list(segments)
            position += duration


class TaggedIdentifier(SpeakerIdentifier):
    name = "tagged-identifier"

    def __init__(self) -> None:
        self.voices: dict[str, PersonId] = {}

    async def enroll(self, person: PersonId, audio: bytes) -> None:
        if (voice := speaker_of(audio)) is not None:
            self.voices[voice] = person

    async def identify(self, audio: bytes) -> Identification:
        person = self.voices.get(speaker_of(audio) or "")
        return Identification(person, 0.95) if person else Identification.unknown()

    async def forget(self, person: PersonId) -> None:
        self.voices = {v: p for v, p in self.voices.items() if p != person}


class DiarizerContract:
    """Implement `diarizer()` and `speech(speaker, seconds)`: audio of that speaker for this model."""

    def diarizer(self) -> Diarizer:
        raise NotImplementedError

    def speech(self, speaker: str, seconds: float) -> bytes:
        raise NotImplementedError

    async def test_two_speakers_get_two_labels_in_order(self) -> None:
        chunks = [self.speech("a", 2.0), self.speech("b", 2.0), self.speech("a", 2.0)]

        async def audio() -> AsyncIterator[bytes]:
            for chunk in chunks:
                yield chunk

        async with self.diarizer() as diarizer:
            final: list[Segment] = []
            async for segmentation in diarizer.diarize(audio()):
                final = segmentation
        assert [s.speaker for s in final][:1] == [final[-1].speaker], "the first speaker keeps their label"
        assert len({s.speaker for s in final}) == 2
        assert all(a.start_s <= b.start_s for a, b in itertools.pairwise(final))


class SpeakerIdentifierContract:
    """Implement `identifier()` and `speech(speaker, seconds)`."""

    def identifier(self) -> SpeakerIdentifier:
        raise NotImplementedError

    def speech(self, speaker: str, seconds: float) -> bytes:
        raise NotImplementedError

    async def test_an_enrolled_voice_is_recognised_and_a_stranger_is_not(self) -> None:
        mathis = PersonId("mathis")
        async with self.identifier() as identifier:
            assert (await identifier.identify(self.speech("mathis", 3.0))).person is None, "nobody enrolled yet"
            await identifier.enroll(mathis, self.speech("mathis", 10.0))
            known = await identifier.identify(self.speech("mathis", 3.0))
            stranger = await identifier.identify(self.speech("someone-else", 3.0))
            await identifier.forget(mathis)
            forgotten = await identifier.identify(self.speech("mathis", 3.0))
        assert known.person == mathis and known.confidence >= identifier.threshold
        assert stranger.person is None and forgotten.person is None

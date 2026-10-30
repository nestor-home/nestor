"""Ports of speaker identity; they may run on the server or on a satellite that reports observations."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator

from nestor.core import Component, PersonId
from nestor.modules.identity.types import Identification, Segment


class Diarizer(Component, ABC):
    """Who speaks when, with anonymous labels stable within one stream.

    Contract (checked by `nestor.testing.identity.DiarizerContract`): each yielded list is the whole
    current segmentation (revisions allowed), segments are ordered and do not overlap for one
    speaker, and the stream ends when the audio ends.
    """

    sample_rate: int = 16000

    @abstractmethod
    def diarize(self, audio: AsyncIterable[bytes]) -> AsyncIterator[list[Segment]]:
        """16-bit mono PCM chunks at `sample_rate` in, segmentations out."""


class SpeakerIdentifier(Component, ABC):
    """Known voices, enrolled with consent.

    Contract (checked by `nestor.testing.identity.SpeakerIdentifierContract`):
    - an enrolled person's other speech is identified as them above `threshold`;
    - nobody enrolled, a stranger, or a forgotten person gives `Identification.unknown()`-like answers
      (`person=None`) — never a guess below the threshold;
    - `forget` removes every trace of the person's voice.
    """

    threshold: float = 0.7

    @abstractmethod
    async def enroll(self, person: PersonId, audio: bytes) -> None: ...

    @abstractmethod
    async def identify(self, audio: bytes) -> Identification: ...

    @abstractmethod
    async def forget(self, person: PersonId) -> None: ...

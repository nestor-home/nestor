"""Speech segments, anonymous session speakers, voiceprints and identification results."""

from dataclasses import dataclass
from typing import NewType

from nestor.core import PersonId

SpeakerLabel = NewType("SpeakerLabel", str)  # anonymous within a session: "spk-0", "spk-1"


@dataclass(frozen=True, slots=True)
class Segment:
    """`speaker` spoke from `start_s` to `end_s` (seconds from the start of the stream). A diarizer may
    revise past segments as it hears more: the latest list wins."""

    start_s: float
    end_s: float
    speaker: SpeakerLabel


@dataclass(frozen=True, slots=True)
class Voiceprint:
    """A model-specific embedding of a voice. Biometric data: stored only with consent, deletable."""

    model: str
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Identification:
    """A known person with a confidence in [0, 1], or `person=None` for someone unknown or unsure."""

    person: PersonId | None
    confidence: float

    @classmethod
    def unknown(cls) -> "Identification":
        return cls(None, 0.0)

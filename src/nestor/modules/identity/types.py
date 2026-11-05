"""Who speaks: the speaker of a turn, voiceprints and what a voice tells about who it is."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

from nestor.core import PersonId

SpeakerLabel = NewType("SpeakerLabel", str)  # anonymous within a session: "spk-0", "spk-1"

type Vector = tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Segment:
    """`speaker` spoke from `start_s` to `end_s` (seconds from the start of the stream). A diarizer may
    revise past segments as it hears more: the latest list wins."""

    start_s: float
    end_s: float
    speaker: SpeakerLabel


class Identified(StrEnum):
    """How the speaker of a turn is known. Only `account` vouches for them: a voice or a name only personalises."""

    ACCOUNT = "account"  # the channel authenticated the sender (a messaging account, the admin)
    VOICE = "voice"  # their voice was recognised
    SAID = "said"  # they said who they are
    UNKNOWN = "unknown"  # someone of the household, nobody knows who: a shared device without recognition


@dataclass(frozen=True, slots=True)
class Speaker:
    """Who said a turn. A satellite is a place: who speaks there is decided turn by turn."""

    person: PersonId | None
    by: Identified
    confidence: float | None = None  # how close the voice is to theirs, for `voice`

    @classmethod
    def account(cls, person: PersonId) -> "Speaker":
        return cls(person, Identified.ACCOUNT)

    @classmethod
    def unknown(cls) -> "Speaker":
        return cls(None, Identified.UNKNOWN)

    @property
    def private(self) -> bool:
        """Whether what belongs to them may be given here: on their own account, or to their recognised voice.
        A name anyone can say is not enough."""
        return self.person is not None and self.by in (Identified.ACCOUNT, Identified.VOICE)


@dataclass(frozen=True, slots=True, kw_only=True)
class VoiceSpace:
    """What a voiceprint means: the model that computed it and its size. Two spaces never mix: a person enrolled
    with one model is enrolled again with another."""

    model: str
    dimensions: int

    @property
    def id(self) -> str:
        return hashlib.sha256(f"voice\0{self.model}\0{self.dimensions}".encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True, kw_only=True)
class Heard:
    """What a voice says about who spoke, before the turn is answered.

    `voiceprint` is unit length, in the space `space`; `None` when the speech was too short to tell. `score` is the
    best person's similarity (cosine), `margin` how far ahead of the next person it is.
    """

    space: str
    voiceprint: Vector | None
    duration_s: float
    person: PersonId | None = None  # recognised: `score` reached the threshold
    score: float = 0.0
    margin: float = 0.0


@dataclass(frozen=True, slots=True, kw_only=True)
class Learned:
    """A voiceprint taken from an everyday turn. `turn` is the turn it comes from, so that a correction removes it;
    `room` where it was said, so that no room fills the person's voice alone."""

    voiceprint: Vector
    turn: str
    room: str
    at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Profile:
    """A person's voice in one space: the anchor from the recording they agreed to, which learning never changes,
    and what was learned since, oldest first."""

    anchor: tuple[Vector, ...]
    learned: tuple[Learned, ...] = ()
    learning: bool = True  # whether everyday turns may still add to it
    enrolled_at: datetime | None = None

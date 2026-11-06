"""A person's voice, a guided recording and its phrases, and who a recording sounds like."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.presentation import Phrasebook
from nestor.core.i18n import Message
from nestor.modules.identity import Enrollment, Problem, VoiceStatus


class VoiceOut(BaseModel):
    enrolled: bool
    learning: bool  # whether everyday turns still improve it
    learned: int  # voiceprints learned since the recording
    enrolled_at: datetime | None
    last_learned_at: datetime | None
    manageable: bool  # whether the caller may record, change or erase it

    @classmethod
    def of(cls, status: VoiceStatus, *, manageable: bool) -> "VoiceOut":
        return cls(
            enrolled=status.enrolled,
            learning=status.learning,
            learned=status.learned,
            enrolled_at=status.enrolled_at,
            last_learned_at=status.last_learned_at,
            manageable=manageable,
        )


class RecordingOut(BaseModel):
    id: str
    person: str
    phrases: list[str]  # to read aloud, in the caller's language
    next: int | None  # the first phrase still to say

    @classmethod
    def of(cls, enrollment: Enrollment, words: Phrasebook) -> "RecordingOut":
        return cls(
            id=enrollment.id,
            person=enrollment.person,
            phrases=[words.text(Message.of(p)) for p in enrollment.phrases],
            next=enrollment.next,
        )


class PhraseOut(BaseModel):
    kept: bool
    problem: Problem | None
    taken: int
    total: int


class RecordingIn(BaseModel):
    learning: bool = True  # agreed in the consent step: improved as they talk


class LearningIn(BaseModel):
    learning: bool


class HeardOut(BaseModel):
    person: str | None  # None: nobody recognised
    name: str | None
    score: float  # how alike, 0 to 1
    threshold: float

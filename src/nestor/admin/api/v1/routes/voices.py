"""People's voices: recording one with consent, a guided recording phrase by phrase, trying recognition, learning
over time, forgetting.

A person records their own voice; an owner records it for someone without an account (a grandmother, a child),
who agrees in person. Phrases come as 16-bit mono WAV at 16 kHz (the browser resamples), one request each: the
server answers whether it is kept, keeps only its voiceprint, and drops the audio.
"""

import io
import wave
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, Response
from pydantic import BaseModel

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import AdminState, state
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.accounts import Scope
from nestor.modules.identity import Enrollment, Problem, Voices, VoiceStatus

router = APIRouter(tags=["voices"])
Reader = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_READ))]
RATE = 16000
WAV = Body(media_type="audio/wav")


class VoiceOut(BaseModel):
    enrolled: bool
    learning: bool  # whether everyday turns still improve it
    learned: int  # voiceprints learned since the recording
    enrolled_at: datetime | None
    last_learned_at: datetime | None
    manageable: bool  # whether the caller may record, change or erase it


class RecordingOut(BaseModel):
    id: str
    person: str
    phrases: list[str]  # to read aloud, in the caller's language
    next: int | None  # the first phrase still to say


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


@router.get("/household/people/{person_id}/voice")
async def get_voice(request: Request, caller: Reader, person_id: str) -> VoiceOut:
    admin = state(request)
    person = _person(admin, person_id)
    return _out(_voices(admin).status(person), may_manage(admin, caller, person))


@router.post("/household/people/{person_id}/voice/recording", status_code=201)
async def start_recording(request: Request, caller: Reader, person_id: str, body: RecordingIn) -> RecordingOut:
    admin = state(request)
    person = _managed(admin, caller, person_id)
    enrollment = _voices(admin).begin(person, by=caller.person, where="admin", learning=body.learning)
    return _recording(caller, enrollment)


@router.put("/voice/recordings/{recording_id}/phrases/{phrase}")
async def say_phrase(
    request: Request, caller: Reader, recording_id: str, phrase: int, audio: Annotated[bytes, WAV]
) -> PhraseOut:
    admin = state(request)
    voices = _voices(admin)
    _managed(admin, caller, voices.enrollment(recording_id).person)
    check = await voices.take(recording_id, phrase, _pcm(audio))
    return PhraseOut(kept=check.ok, problem=check.problem, taken=check.taken, total=check.total)


@router.post("/voice/recordings/{recording_id}/finish")
async def finish_recording(request: Request, caller: Reader, recording_id: str) -> VoiceOut:
    admin = state(request)
    voices = _voices(admin)
    person = _managed(admin, caller, voices.enrollment(recording_id).person)
    await voices.finish(recording_id)
    return _out(voices.status(person), manageable=True)


@router.delete("/voice/recordings/{recording_id}", status_code=204)
async def abandon_recording(request: Request, caller: Reader, recording_id: str) -> Response:
    admin = state(request)
    voices = _voices(admin)
    _managed(admin, caller, voices.enrollment(recording_id).person)
    voices.abandon(recording_id)
    return Response(status_code=204)


@router.post("/voice/hear")
async def hear(request: Request, caller: Reader, audio: Annotated[bytes, WAV]) -> HeardOut:
    """Who a recording is, as the satellites would recognise it: to try one's voice once recorded."""
    admin = state(request)
    voices = _voices(admin)
    heard = await voices.hear(_pcm(audio))
    name = admin.nestor.household.name_of(heard.person, "") or None
    return HeardOut(person=heard.person, name=name, score=round(heard.score, 3), threshold=voices.threshold)


@router.put("/household/people/{person_id}/voice/learning")
async def set_learning(request: Request, caller: Reader, person_id: str, body: LearningIn) -> VoiceOut:
    admin = state(request)
    person = _managed(admin, caller, person_id)
    voices = _voices(admin)
    await voices.set_learning(person, body.learning, by=caller.person)
    return _out(voices.status(person), manageable=True)


@router.delete("/household/people/{person_id}/voice")
async def forget_voice(request: Request, caller: Reader, person_id: str, learned_only: bool = False) -> VoiceOut:
    """Erase the person's voice, or only what was learned since the recording."""
    admin = state(request)
    person = _managed(admin, caller, person_id)
    voices = _voices(admin)
    await voices.forget(person, by=caller.person, learned_only=learned_only)
    return _out(voices.status(person), manageable=True)


def may_manage(admin: AdminState, caller: Caller, person: PersonId) -> bool:
    """Their own voice; an owner, the voice of someone without an account."""
    if caller.person == person:
        return True
    return caller.principal.can(Scope.OWNERS_MANAGE) and admin.accounts.of_person(person) is None


def _voices(admin: AdminState) -> Voices:
    if admin.nestor.voices is None:
        raise not_found("voices_off")
    return admin.nestor.voices


def _person(admin: AdminState, person_id: str) -> PersonId:
    if not any(p.id == person_id for p in admin.nestor.household.people):
        raise not_found("person_unknown")
    return PersonId(person_id)


def _managed(admin: AdminState, caller: Caller, person_id: str) -> PersonId:
    person = _person(admin, person_id)
    if not may_manage(admin, caller, person):
        raise ApiError(403, "voice_not_yours")
    return person


def _pcm(audio: bytes) -> bytes:
    """The samples of a 16-bit mono WAV at 16 kHz."""
    try:
        with wave.open(io.BytesIO(audio)) as found:
            if (found.getnchannels(), found.getsampwidth(), found.getframerate()) != (1, 2, RATE):
                raise ApiError(400, "audio_format")
            return found.readframes(found.getnframes())
    except (wave.Error, EOFError):
        raise ApiError(400, "audio_format") from None


def _recording(caller: Caller, enrollment: Enrollment) -> RecordingOut:
    return RecordingOut(
        id=enrollment.id,
        person=enrollment.person,
        phrases=[caller.phrasebook.text(Message.of(p)) for p in enrollment.phrases],
        next=enrollment.next,
    )


def _out(status: VoiceStatus, manageable: bool) -> VoiceOut:
    return VoiceOut(
        enrolled=status.enrolled,
        learning=status.learning,
        learned=status.learned,
        enrolled_at=status.enrolled_at,
        last_learned_at=status.last_learned_at,
        manageable=manageable,
    )

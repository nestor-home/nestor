"""People's voices: recording one with consent, a guided recording phrase by phrase, trying recognition, learning
over time, forgetting.

A person records their own voice; an owner records it for someone without an account (a grandmother, a child),
who agrees in person. Phrases come as 16-bit mono WAV at 16 kHz (the browser resamples), one request each: the
server answers whether it is kept, keeps only its voiceprint, and drops the audio.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, Response

from nestor.admin.api.v1.access import household_person, managed_voice, manages_voice
from nestor.admin.api.v1.errors import not_found
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.voices.audio import pcm
from nestor.admin.api.v1.voices.schemas import (
    HeardOut,
    LearningIn,
    PhraseOut,
    RecordingIn,
    RecordingOut,
    VoiceOut,
)
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.identity import Voices

router = APIRouter(tags=["voices"])
Reader = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_READ))]
WAV = Body(media_type="audio/wav")


def voices_of(request: Request) -> Voices:
    """The household's voices, else 404 when recognising them is off."""
    voices = state(request).nestor.voices
    if voices is None:
        raise not_found("voices_off")
    return voices


Recognition = Annotated[Voices, Depends(voices_of)]


@router.get("/household/people/{person_id}/voice")
async def get_voice(request: Request, caller: Reader, voices: Recognition, person_id: str) -> VoiceOut:
    admin = state(request)
    person = household_person(admin, person_id)
    return VoiceOut.of(voices.status(person), manageable=manages_voice(admin, caller, person))


@router.post("/household/people/{person_id}/voice/recording", status_code=201)
async def start_recording(
    request: Request, caller: Reader, voices: Recognition, person_id: str, body: RecordingIn
) -> RecordingOut:
    person = managed_voice(state(request), caller, person_id)
    enrollment = voices.begin(person, by=caller.person, where="admin", learning=body.learning)
    return RecordingOut.of(enrollment, caller.phrasebook)


@router.put("/voice/recordings/{recording_id}/phrases/{phrase}")
async def say_phrase(
    request: Request, caller: Reader, voices: Recognition, recording_id: str, phrase: int, audio: Annotated[bytes, WAV]
) -> PhraseOut:
    managed_voice(state(request), caller, voices.enrollment(recording_id).person)
    check = await voices.take(recording_id, phrase, pcm(audio))
    return PhraseOut(kept=check.ok, problem=check.problem, taken=check.taken, total=check.total)


@router.post("/voice/recordings/{recording_id}/finish")
async def finish_recording(request: Request, caller: Reader, voices: Recognition, recording_id: str) -> VoiceOut:
    person = managed_voice(state(request), caller, voices.enrollment(recording_id).person)
    await voices.finish(recording_id)
    return VoiceOut.of(voices.status(person), manageable=True)


@router.delete("/voice/recordings/{recording_id}", status_code=204)
async def abandon_recording(request: Request, caller: Reader, voices: Recognition, recording_id: str) -> Response:
    managed_voice(state(request), caller, voices.enrollment(recording_id).person)
    voices.abandon(recording_id)
    return Response(status_code=204)


@router.post("/voice/hear")
async def hear(request: Request, caller: Reader, voices: Recognition, audio: Annotated[bytes, WAV]) -> HeardOut:
    """Who a recording is, as the satellites would recognise it: to try one's voice once recorded."""
    heard = await voices.hear(pcm(audio))
    name = state(request).nestor.household.name_of(heard.person, "") or None
    return HeardOut(person=heard.person, name=name, score=round(heard.score, 3), threshold=voices.threshold)


@router.put("/household/people/{person_id}/voice/learning")
async def set_learning(
    request: Request, caller: Reader, voices: Recognition, person_id: str, body: LearningIn
) -> VoiceOut:
    person = managed_voice(state(request), caller, person_id)
    await voices.set_learning(person, body.learning, by=caller.person)
    return VoiceOut.of(voices.status(person), manageable=True)


@router.delete("/household/people/{person_id}/voice")
async def forget_voice(
    request: Request, caller: Reader, voices: Recognition, person_id: str, learned_only: bool = False
) -> VoiceOut:
    """Erase the person's voice, or only what was learned since the recording."""
    person = managed_voice(state(request), caller, person_id)
    await voices.forget(person, by=caller.person, learned_only=learned_only)
    return VoiceOut.of(voices.status(person), manageable=True)

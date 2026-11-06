"""Recording a voice from the admin, phrase by phrase, trying it, learning it over time, erasing it."""

import io
import wave
from pathlib import Path

import httpx

from nestor.modules.accounts import Role
from nestor.modules.identity import VoiceEnrolled, VoiceForgotten
from nestor.testing.identity import tagged

from ...harness import Api, Harness


def wav(audio: bytes, *, rate: int = 16000) -> bytes:
    found = io.BytesIO()
    with wave.open(found, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(audio)
    return found.getvalue()


async def send_wav(api: Api, method: str, path: str, audio: bytes) -> httpx.Response:
    headers = {"X-CSRF-Token": api.csrf, "Content-Type": "audio/wav"}
    return await api.client.request(method, path, content=audio, headers=headers)


async def test_a_person_records_their_voice_phrase_by_phrase_and_is_then_recognised(tmp_path: Path) -> None:
    async with Harness(tmp_path, voices=True) as admin:
        api = await admin.api()
        before = (await api.get("/api/v1/household/people/mathis/voice")).json()
        started = await api.post("/api/v1/household/people/mathis/voice/recording", {"learning": True})
        recording = started.json()
        assert started.status_code == 201 and len(recording["phrases"]) == 5
        assert recording["phrases"][0] == "Nestor, allume la lumière du salon."  # in the reader's language

        too_short = await send_wav(api, "PUT", f"/api/v1/voice/recordings/{recording['id']}/phrases/0",
                                   wav(tagged("mathis", 0.5)))  # fmt: skip
        assert too_short.json() == {"kept": False, "problem": "too_short", "taken": 0, "total": 5}
        for phrase in range(5):
            said = await send_wav(api, "PUT", f"/api/v1/voice/recordings/{recording['id']}/phrases/{phrase}",
                                  wav(tagged("mathis", take=phrase)))  # fmt: skip
            assert said.json()["kept"], said.text
        done = (await api.post(f"/api/v1/voice/recordings/{recording['id']}/finish")).json()

        heard = (await send_wav(api, "POST", "/api/v1/voice/hear", wav(tagged("mathis", take=9)))).json()
        stranger = (await send_wav(api, "POST", "/api/v1/voice/hear", wav(tagged("someone")))).json()
        enrolled = await admin.nestor.journal.history(VoiceEnrolled)
        stopped = (await api.put("/api/v1/household/people/mathis/voice/learning", {"learning": False})).json()
        learned_gone = (await api.delete("/api/v1/household/people/mathis/voice?learned_only=true")).json()
        erased = (await api.delete("/api/v1/household/people/mathis/voice")).json()
        forgotten = await admin.nestor.journal.history(VoiceForgotten)
    assert not before["enrolled"] and before["manageable"]
    assert done["enrolled"] and done["learning"] and done["learned"] == 0
    assert (heard["person"], heard["name"]) == ("mathis", "Mathis") and heard["score"] >= heard["threshold"]
    assert stranger["person"] is None
    assert [(e.person, e.where) for e in enrolled] == [("mathis", "admin")]
    assert stopped["learning"] is False and learned_gone["enrolled"] and not erased["enrolled"]
    assert [e.learned_only for e in forgotten] == [True, False]


async def test_only_the_person_or_an_owner_for_someone_without_an_account_records_a_voice(tmp_path: Path) -> None:
    async with Harness(tmp_path, voices=True) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        owner, mathilde = await admin.api(), await admin.api("mathilde")
        others = await mathilde.post("/api/v1/household/people/mathis/voice/recording", {})
        hers = await mathilde.post("/api/v1/household/people/mathilde/voice/recording", {})
        for_her = await owner.post("/api/v1/household/people/mathilde/voice/recording", {})
        assert (await owner.get("/api/v1/household/people/mathilde/voice")).json()["manageable"] is False
    assert others.status_code == 403 and others.json()["error"]["code"] == "voice_not_yours"
    assert hers.status_code == 201
    assert for_her.status_code == 403, "she has an account: she records it herself"


async def test_an_owner_records_the_voice_of_someone_without_an_account(tmp_path: Path) -> None:
    async with Harness(tmp_path, voices=True) as admin:
        started = await (await admin.api()).post("/api/v1/household/people/lucie/voice/recording", {})
        assert started.status_code == 201 and started.json()["person"] == "lucie"


async def test_a_recording_abandoned_or_in_a_wrong_format_keeps_nothing(tmp_path: Path) -> None:
    async with Harness(tmp_path, voices=True) as admin:
        api = await admin.api()
        recording = (await api.post("/api/v1/household/people/mathis/voice/recording", {})).json()
        stereo = await send_wav(api, "PUT", f"/api/v1/voice/recordings/{recording['id']}/phrases/0",
                                wav(tagged("mathis"), rate=44100))  # fmt: skip
        garbage = await send_wav(api, "POST", "/api/v1/voice/hear", b"not a wav")
        assert (await api.delete(f"/api/v1/voice/recordings/{recording['id']}")).status_code == 204
        gone = await send_wav(api, "PUT", f"/api/v1/voice/recordings/{recording['id']}/phrases/0",
                              wav(tagged("mathis")))  # fmt: skip
    assert stereo.status_code == 400 and stereo.json()["error"]["code"] == "audio_format"
    assert garbage.status_code == 400
    assert gone.status_code == 400 and "start again" in gone.json()["error"]["message"]


async def test_without_a_voice_model_voices_are_off(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        found = await (await admin.api()).get("/api/v1/household/people/mathis/voice")
    assert found.status_code == 404 and found.json()["error"]["code"] == "voices_off"

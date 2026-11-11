import json
import os
import re
from pathlib import Path

import httpx
import pytest

from nestor.adapters.models.elevenlabs import speech, transcription
from nestor.adapters.models.pipecat.eager import EagerSentenceFlush
from nestor.core import ProviderError
from nestor.core.i18n import Locale
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.runtime.plugins import Services
from nestor.testing.channels import OGG, SpeechModelContract, TranscriptionModelContract
from nestor.testing.i18n import EchoLocalizer

SPEECH = {"api_key": "xi-test", "voice_id": "GPAQQPp9dazaB2bl4zg9"}


def test_the_api_key_is_never_shown() -> None:
    assert "xi-test" not in repr(speech.ElevenLabsSpeechSettings.model_validate(SPEECH))
    assert "xi-test" not in repr(transcription.ElevenLabsTranscriptionSettings.model_validate({"api_key": "xi-test"}))


def test_each_session_gets_its_own_services_and_speech_does_not_wait_for_more_text(tmp_path: Path) -> None:
    services = Services(tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    ears = transcription.plugin.create({"api_key": "xi-test", "language": "fr"}, "ears", services)
    mouth = speech.plugin.create(SPEECH, "mouth", services)
    assert isinstance(ears, TranscriptionModel) and isinstance(mouth, SpeechModel)
    assert ears.stt() is not ears.stt()
    assert isinstance(mouth.tts(), EagerSentenceFlush), "a complete sentence is spoken without waiting for more"


FILE_PART = rb'name="file"; filename="[^"]*"\r\nContent-Type: [^\r]+\r\n\r\n(.*?)\r\n--'


class FakeElevenLabs:
    """The two HTTP endpoints recordings use: speech to text answers with what the recording holds, text to speech
    with an OGG made of the text. Any other key is refused, as ElevenLabs does."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers["xi-api-key"] != "xi-test":
            return httpx.Response(401, json={"detail": {"status": "invalid_api_key", "message": "Invalid API key"}})
        if request.url.path == "/v1/speech-to-text":
            [recording] = re.findall(
                rb'name="file"; filename="[^"]*"\r\nContent-Type: [^\r]+\r\n\r\n(.*?)\r\n--', request.content, re.S
            )
            return httpx.Response(200, json={"language_code": "fra", "text": f" {recording.decode()} "})
        if request.url.path.startswith("/v1/text-to-speech/"):
            return httpx.Response(200, content=OGG + json.loads(request.content)["text"].encode())
        return httpx.Response(404)


class TestElevenLabsTranscription(TranscriptionModelContract):
    fake = FakeElevenLabs()

    def model(self, api_key: str = "xi-test") -> TranscriptionModel:
        return transcription.ElevenLabsTranscription(
            api_key=api_key,
            model="scribe_v2_realtime",
            file_model="scribe_v2",
            language="fr",
            name="ears",
            transport=self.fake.transport,
        )

    def recording(self) -> tuple[bytes, str, str]:
        return b"bonjour Nestor", "audio/ogg", "bonjour"

    def unavailable_model(self) -> TranscriptionModel:
        return self.model(api_key="xi-wrong")

    async def test_recordings_use_the_file_model_in_the_language_said(self) -> None:
        async with self.model() as model:
            await model.transcribe(b"salut", "audio/ogg")
        body = self.fake.requests[-1].content
        assert b'name="model_id"\r\n\r\nscribe_v2\r\n' in body, "the realtime model cannot read files"
        assert b'name="language_code"\r\n\r\nfr\r\n' in body


async def test_a_transcription_answer_that_is_not_json_is_a_provider_error() -> None:
    page = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>maintenance</html>"))
    model = transcription.ElevenLabsTranscription(
        api_key="xi-test", model="m", file_model="scribe_v2", language="fr", name="ears", transport=page
    )
    async with model:
        with pytest.raises(ProviderError):
            await model.transcribe(b"opus", "audio/ogg")


class TestElevenLabsSpeech(SpeechModelContract):
    fake = FakeElevenLabs()

    def model(self, api_key: str = "xi-test") -> SpeechModel:
        return speech.ElevenLabsSpeech(
            api_key=api_key, model="eleven_v4_turbo", voice_id="victor", name="mouth", transport=self.fake.transport
        )

    def unavailable_model(self) -> SpeechModel:
        return self.model(api_key="xi-wrong")

    async def test_the_model_goes_in_the_body(self) -> None:
        async with self.model() as model:
            await model.synthesize("Bonjour.")
        request = self.fake.requests[-1]
        assert json.loads(request.content)["model_id"] == "eleven_v4_turbo", "outside the body, it is ignored"
        assert request.url.path == "/v1/text-to-speech/victor"


ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY", "")


@pytest.mark.live
@pytest.mark.skipif(not ELEVENLABS_KEY, reason="ELEVENLABS_API_KEY is not set")
class TestElevenLabsSpeechLive(SpeechModelContract):
    """The contract against ElevenLabs, with a French voice of the library."""

    def model(self, api_key: str = ELEVENLABS_KEY) -> SpeechModel:
        return speech.ElevenLabsSpeech(
            api_key=api_key, model="eleven_v4_turbo", voice_id="GPAQQPp9dazaB2bl4zg9", name="live"
        )

    def unavailable_model(self) -> SpeechModel:
        return self.model(api_key="xi-invalid")

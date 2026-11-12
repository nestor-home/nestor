"""OpenAI-compatible voice: the transcription and speech contracts over mocked `/audio/*` endpoints, as OpenAI,
Groq or a local Kokoro-FastAPI server answer, and the services the satellites' voice runs."""

import json
import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from nestor.adapters.models.openai_compatible import speech, transcription
from nestor.adapters.models.openai_compatible.speech import OpenAICompatibleSpeech
from nestor.adapters.models.openai_compatible.transcription import OpenAICompatibleTranscription
from nestor.adapters.models.pipecat.eager import EagerSentenceFlush
from nestor.core.i18n import Locale
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.runtime.plugins import Services
from nestor.testing.channels import OGG, SpeechModelContract, TranscriptionModelContract
from nestor.testing.i18n import EchoLocalizer

BASE_URL = "https://voice.test/v1"
KEY = "sk-voice-0123456789"
FILE_PART = rb'name="file"; filename="([^"]*)"\r\nContent-Type: [^\r]+\r\n\r\n(.*?)\r\n--'


def heard(request: httpx.Request) -> httpx.Response:
    """What the recording holds, when the request names the language and a file whose extension says its format."""
    if request.headers.get("Authorization") != f"Bearer {KEY}":
        return httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {KEY[:6]}…"}})
    [(name, recording)] = re.findall(FILE_PART, request.content, re.S)
    assert b'name="language"\r\n\r\nfr\r\n' in request.content, "Whisper guesses the language otherwise"
    assert name.endswith(b".ogg"), "some servers read the format from the extension"
    return httpx.Response(200, json={"text": f" {recording.decode()} "})


def spoken(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if body["response_format"] != "opus":
        return httpx.Response(200, content=b"ID3 an mp3")  # the API's default
    return httpx.Response(200, content=OGG + body["input"].encode())


@pytest.fixture(autouse=True)
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/audio/transcriptions").mock(side_effect=heard)
        router.post(f"{BASE_URL}/audio/speech").mock(side_effect=spoken)
        router.post("https://down.test/v1/audio/speech").respond(503, json={"error": {"message": "overloaded"}})
        yield router


class TestTranscription(TranscriptionModelContract):
    def model(self) -> OpenAICompatibleTranscription:
        return OpenAICompatibleTranscription(base_url=BASE_URL, api_key=KEY, model="whisper-1", language="fr")

    def recording(self) -> tuple[bytes, str, str]:
        return b"rappelle-moi le pain", "audio/ogg; codecs=opus", "pain"

    def unavailable_model(self) -> OpenAICompatibleTranscription:
        return OpenAICompatibleTranscription(base_url=BASE_URL, api_key="sk-revoked", model="whisper-1", language="fr")


class TestSpeech(SpeechModelContract):
    def model(self) -> OpenAICompatibleSpeech:
        return OpenAICompatibleSpeech(base_url=BASE_URL, api_key=None, model="kokoro", voice="ff_siwis")

    def unavailable_model(self) -> OpenAICompatibleSpeech:
        return OpenAICompatibleSpeech(base_url="https://down.test/v1", api_key=None, model="kokoro", voice="ff_siwis")


def test_each_session_gets_its_own_services_and_speech_does_not_wait_for_more_text(tmp_path: Path) -> None:
    services = Services(tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    endpoint = {"base_url": "http://localhost:8880/v1"}  # a local server asks for no key
    ears = transcription.plugin.create(endpoint | {"model": "whisper-1", "language": "fr"}, "ears", services)
    mouth = speech.plugin.create(endpoint | {"model": "kokoro", "voice": "ff_siwis"}, "mouth", services)
    assert isinstance(ears, TranscriptionModel) and isinstance(mouth, SpeechModel)
    assert ears.stt() is not ears.stt()
    assert isinstance(mouth.tts(), EagerSentenceFlush), "a complete sentence is spoken without waiting for more"

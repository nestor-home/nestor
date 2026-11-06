from pathlib import Path

from nestor.adapters.models.elevenlabs import speech, transcription
from nestor.adapters.models.pipecat.eager import EagerSentenceFlush
from nestor.core.i18n import Locale
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.runtime.plugins import Services
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

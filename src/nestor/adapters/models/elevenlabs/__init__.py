"""ElevenLabs, by type:

- `transcription`: Scribe, realtime over WebSocket for the satellites' voice, over HTTP for recordings (a voice
  message) (`transcription.py`);
- `speech`: its voices, over the Text-to-Dialogue WebSocket for the voice, the text-to-speech HTTP endpoint for
  recordings (`speech.py`).

Each is configured by `api_key` and its model (`settings.py`); the voice runs Pipecat's ElevenLabs services (the
`voice` extra). Recordings go through its HTTP API (`api.py`).
"""

from nestor.adapters.models.elevenlabs.settings import (
    ElevenLabsSpeechSettings,
    ElevenLabsTranscriptionSettings,
    build_speech,
    build_transcription,
)
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.runtime.plugins import Family, Plugin

transcription = Plugin(
    Family.MODEL,
    "elevenlabs",
    ElevenLabsTranscriptionSettings,
    build_transcription,
    requires="nestor-home[voice]",
    serves=TranscriptionModel,
)
speech = Plugin(
    Family.MODEL,
    "elevenlabs",
    ElevenLabsSpeechSettings,
    build_speech,
    requires="nestor-home[voice]",
    serves=SpeechModel,
)

__all__ = ["speech", "transcription"]

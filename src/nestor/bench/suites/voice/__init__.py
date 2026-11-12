"""Voice benches: how well a transcription model hears French recordings, and how fast and how clearly a speech
model speaks, both at what they cost on this machine or through their provider."""

from nestor.bench.suites.voice.speech import Speech
from nestor.bench.suites.voice.transcription import Transcription

transcription = Transcription()
speech = Speech()

__all__ = ["Speech", "Transcription", "speech", "transcription"]

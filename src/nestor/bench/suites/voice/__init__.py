"""Voice benches: how well a transcription model hears French recordings, how fast and how clearly a speech model
speaks, both at what they cost on this machine or through their provider, and which words over the assistant's
voice cut it off."""

from nestor.bench.suites.voice.acknowledgements import Acknowledgements
from nestor.bench.suites.voice.speech import Speech
from nestor.bench.suites.voice.transcription import Transcription

transcription = Transcription()
speech = Speech()
acknowledgements = Acknowledgements()

__all__ = ["Acknowledgements", "Speech", "Transcription", "acknowledgements", "speech", "transcription"]

"""sherpa-onnx: models run on the CPU, on this machine, so nothing said leaves the house and no key is needed. By type:

- `speaker`: voiceprints from a small speaker model (the `voice-id` extra) (`speaker.py`);
- `transcription`: speech recognition, for recordings and the satellites' voice (the `voice` and `voice-id` extras)
  (`transcription.py`, its Pipecat service in `pipeline.py`, recordings decoded in `audio.py`).

`model` names one of the catalogue (`catalogue.py`), downloaded once from the sherpa-onnx releases under the data
folder and checked against its pinned sha256 (`releases.py`); a speaker model may also be an `.onnx` file of one's
own, with its `threshold`. Each type's settings and build are in `settings.py`.
"""

from nestor.adapters.models.sherpa_onnx.settings import (
    SherpaOnnxSpeakerSettings,
    SherpaOnnxTranscriptionSettings,
    build_speaker,
    build_transcription,
)
from nestor.modules.channels import TranscriptionModel
from nestor.modules.identity import SpeakerModel
from nestor.runtime.plugins import Family, Plugin

speaker = Plugin(
    Family.MODEL,
    "sherpa-onnx",
    SherpaOnnxSpeakerSettings,
    build_speaker,
    requires="nestor-home[voice-id]",
    serves=SpeakerModel,
)
transcription = Plugin(
    Family.MODEL,
    "sherpa-onnx",
    SherpaOnnxTranscriptionSettings,
    build_transcription,
    requires="nestor-home[voice,voice-id]",
    serves=TranscriptionModel,
)

__all__ = ["speaker", "transcription"]

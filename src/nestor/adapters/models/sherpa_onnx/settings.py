"""What configures sherpa-onnx's speaker and transcription models, and how they are built."""

from typing import Self

from pydantic import Field, PositiveInt, model_validator

from nestor.adapters.models.sherpa_onnx.catalogue import SPEAKERS, TRANSCRIPTIONS
from nestor.adapters.models.sherpa_onnx.speaker import SherpaOnnxSpeaker
from nestor.adapters.models.sherpa_onnx.transcription import SherpaOnnxTranscription
from nestor.runtime.plugins import AdapterSettings, Services


class SherpaOnnxSpeakerSettings(AdapterSettings):
    """A voice model run by sherpa-onnx."""

    # a catalogue name, or an `.onnx` path; the admin shows the mark of whoever published a catalogue model
    model: str = Field(
        json_schema_extra={"examples": list(SPEAKERS), "brands": {name: m.brand for name, m in SPEAKERS.items()}}
    )
    # CPU threads of one voiceprint: a Raspberry Pi has 4 cores, and the voice pipeline needs the others
    threads: PositiveInt = Field(default=1, le=16, json_schema_extra={"advanced": True})
    # the similarity from which two voices are one: the catalogue's by default, required for a file of one's own
    threshold: float | None = Field(default=None, gt=0, lt=1, json_schema_extra={"advanced": True})

    @model_validator(mode="after")
    def _calibrated(self) -> Self:
        if self.model not in SPEAKERS and self.threshold is None:
            known = ", ".join(SPEAKERS)
            raise ValueError(f"{self.model!r} is not in the catalogue ({known}): give its `threshold`")
        return self


def build_speaker(settings: SherpaOnnxSpeakerSettings, name: str, services: Services) -> SherpaOnnxSpeaker:
    import sherpa_onnx  # noqa: F401 - the extra is checked when the configuration is built, not at the first turn

    return SherpaOnnxSpeaker(
        model=settings.model,
        data_dir=services.data_dir,
        threads=settings.threads,
        threshold=settings.threshold,
        provider=name,
    )


class SherpaOnnxTranscriptionSettings(AdapterSettings):
    """A speech recognition model run by sherpa-onnx on this machine."""

    model: str = Field(
        default="parakeet-v3",
        json_schema_extra={
            "examples": list(TRANSCRIPTIONS),
            "brands": {name: m.brand for name, m in TRANSCRIPTIONS.items()},
        },
    )
    # CPU threads of one transcription: a Raspberry Pi has 4 cores, and the voice pipeline needs the others
    threads: PositiveInt = Field(default=2, le=16, json_schema_extra={"advanced": True})


def build_transcription(
    settings: SherpaOnnxTranscriptionSettings, name: str, services: Services
) -> SherpaOnnxTranscription:
    import sherpa_onnx  # noqa: F401 - the extra is checked when the configuration is built, not at the first turn

    return SherpaOnnxTranscription(
        model=settings.model, data_dir=services.data_dir, threads=settings.threads, provider=name
    )

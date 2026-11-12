"""Speech recognition with sherpa-onnx (`pip install 'nestor-home[voice,voice-id]'`): a model run on the CPU, on
this machine, so nothing said leaves the house and no key is needed.

`model` names one of the catalogue below, downloaded once from the sherpa-onnx releases into
`<data_dir>/models/speech/`, checked against its pinned sha256 and unpacked there. Parakeet TDT v3 hears 25 European
languages, French and English among them, and finds the language by itself: there is nothing to set.

Recordings (a voice message, OGG/Opus or any format FFmpeg reads) are decoded by PyAV, which the voice extra
installs. The voice of satellites runs it segment by segment: the pipeline's voice activity detection cuts each
turn, transcribed whole (0.26 s for 4 s of speech on an Apple M-series laptop, not measured on a Raspberry Pi)."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field, PositiveInt

from nestor.adapters.models.pipecat import SAMPLE_RATE, PipecatTranscription
from nestor.adapters.models.sherpa_onnx.common import fetch_archive
from nestor.core import ContractError, ProviderError
from nestor.modules.channels import TranscriptionModel
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Services

if TYPE_CHECKING:
    import numpy
    import sherpa_onnx
    from pipecat.services.stt_service import STTService

RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
FOLDER = Path("models") / "speech"  # under the data folder


@dataclass(frozen=True, slots=True, kw_only=True)
class Catalogued:
    """A speech recognition model of the sherpa-onnx releases: a transducer (encoder, decoder, joiner)."""

    archive: str
    sha256: str
    encoder: str
    decoder: str
    joiner: str
    kind: str  # sherpa-onnx's `model_type`
    brand: str  # who published the model: the mark the admin shows for it

    @property
    def folder(self) -> str:
        return self.archive.removesuffix(".tar.bz2")


CATALOGUE: Mapping[str, Catalogued] = {
    "parakeet-v3": Catalogued(
        archive="sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2",
        sha256="1495e91b59d7fc53ddca91f3431758ec99f8fa253fdb0e1e851be0f72b14b0f9",  # 487 MB
        encoder="encoder.int8.onnx",
        decoder="decoder.int8.onnx",
        joiner="joiner.int8.onnx",
        kind="nemo_transducer",  # 25 European languages, found by itself; CC-BY-4.0 (NVIDIA)
        brand="nvidia",
    ),
}


class SherpaOnnxTranscription(PipecatTranscription):
    """Contract: `start` fetches the model when it is not there yet and loads it; each transcription runs its own
    stream in a worker thread, so recordings and turns may be heard at once."""

    name = "sherpa-onnx"

    def __init__(
        self, *, model: str, data_dir: Path, threads: int = 2, release: str = RELEASE, provider: str = "sherpa-onnx"
    ) -> None:
        if model not in CATALOGUE:
            raise ContractError(f"{provider}: {model!r} is not in the catalogue ({', '.join(CATALOGUE)})")
        self._model, self._catalogued = model, CATALOGUE[model]
        self._threads, self._release, self._provider = threads, release, provider
        self._folder = data_dir / FOLDER
        self._recognizer: sherpa_onnx.OfflineRecognizer | None = None
        self.brand = self._catalogued.brand

    def details(self) -> Mapping[str, str]:
        return {"model": self._model, "threads": str(self._threads)}

    async def start(self) -> None:
        model = self._catalogued
        into, archive = self._folder / model.folder, self._folder / model.archive
        await fetch_archive(self._release + model.archive, archive, into, model.sha256, provider=self._provider)
        self._recognizer = await asyncio.to_thread(self._load)

    async def close(self) -> None:
        self._recognizer = None

    def _load(self) -> "sherpa_onnx.OfflineRecognizer":
        import sherpa_onnx

        model = self._catalogued
        found = self._folder / model.folder / model.folder  # the archive holds its own folder
        try:
            return sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(found / model.encoder),
                decoder=str(found / model.decoder),
                joiner=str(found / model.joiner),
                tokens=str(found / "tokens.txt"),
                model_type=model.kind,
                num_threads=self._threads,
            )
        except (RuntimeError, ValueError) as error:
            raise ProviderError(self._provider, f"cannot load {self._model}: {error}", transient=False) from None

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        samples = await asyncio.to_thread(_decoded, audio, self._provider)
        return await self.hear(samples)

    async def hear(self, samples: "numpy.ndarray") -> str:
        """What is said in mono `SAMPLE_RATE` samples between -1 and 1."""
        recognizer = self._recognizer
        if recognizer is None:
            raise ContractError(f"{self._provider}: used before start()")
        return await asyncio.to_thread(_recognized, recognizer, samples)

    def stt(self) -> "STTService":
        from nestor.adapters.models.sherpa_onnx.pipeline import SherpaSegmentedSTT

        return SherpaSegmentedSTT(self)


def _recognized(recognizer: "sherpa_onnx.OfflineRecognizer", samples: "numpy.ndarray") -> str:
    stream = recognizer.create_stream()
    stream.accept_waveform(SAMPLE_RATE, samples)
    recognizer.decode_stream(stream)
    return stream.result.text.strip()


def _decoded(audio: bytes, provider: str) -> "numpy.ndarray":
    """A recording as mono `SAMPLE_RATE` float samples, whatever its format."""
    import io
    import itertools

    import av
    import numpy

    resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
    chunks = []
    try:
        with av.open(io.BytesIO(audio), mode="r") as container:
            for frame in itertools.chain(container.decode(audio=0), [None]):  # `None` flushes the resampler
                chunks += [converted.to_ndarray().reshape(-1) for converted in resampler.resample(frame)]
    except (av.FFmpegError, ValueError) as error:
        raise ProviderError(provider, f"cannot decode the recording: {error}", transient=False) from None
    return numpy.concatenate(chunks) if chunks else numpy.zeros(0, numpy.float32)


class SherpaOnnxTranscriptionSettings(AdapterSettings):
    """A speech recognition model run by sherpa-onnx on this machine."""

    model: str = Field(
        default="parakeet-v3",
        json_schema_extra={"examples": list(CATALOGUE), "brands": {name: m.brand for name, m in CATALOGUE.items()}},
    )
    # CPU threads of one transcription: a Raspberry Pi has 4 cores, and the voice pipeline needs the others
    threads: PositiveInt = Field(default=2, le=16, json_schema_extra={"advanced": True})


def build(settings: SherpaOnnxTranscriptionSettings, name: str, services: Services) -> SherpaOnnxTranscription:
    import sherpa_onnx  # noqa: F401 - the extra is checked when the configuration is built, not at the first turn

    return SherpaOnnxTranscription(
        model=settings.model, data_dir=services.data_dir, threads=settings.threads, provider=name
    )


plugin = Plugin(
    Family.MODEL,
    "sherpa-onnx",
    SherpaOnnxTranscriptionSettings,
    build,
    requires="nestor-home[voice,voice-id]",
    serves=TranscriptionModel,
)

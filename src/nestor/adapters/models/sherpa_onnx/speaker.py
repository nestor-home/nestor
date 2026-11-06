"""Voiceprints with sherpa-onnx (`pip install 'nestor-home[voice-id]'`): a small speaker model run on the CPU, on
this machine, so no voice leaves the house.

`model` names one of the catalogue below, downloaded once from the sherpa-onnx releases into
`<data_dir>/models/voices/` and checked against its pinned sha256, or the path of an `.onnx` file of one's own
(any speaker model sherpa-onnx loads; its `threshold` must then be given, since nobody calibrated it).

Each catalogued model carries the threshold calibrated on the `speaker-id` bench: the similarity at which one
pair of different voices in a hundred is taken for the same. The WeSpeaker models of the same releases are left
out (sherpa-onnx does not take the mean off their features), and so is 3D-Speaker's English CAM++: they barely tell
voices apart (equal error rate 0.12 to 0.46 on the bench).
"""

import asyncio
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

import httpx
from pydantic import Field, PositiveInt, model_validator

from nestor.core import ContractError, ProviderError
from nestor.modules.identity import SpeakerModel, Vector, VoiceSpace
from nestor.modules.identity.audio import samples
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Services

if TYPE_CHECKING:
    import sherpa_onnx

RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"  # their spelling
FOLDER = Path("models") / "voices"  # under the data folder


@dataclass(frozen=True, slots=True, kw_only=True)
class Catalogued:
    """A speaker model of the sherpa-onnx releases, with what the bench measured of it."""

    file: str
    sha256: str
    size: int  # bytes on disk
    dimensions: int
    threshold: float  # calibrated on the `speaker-id` bench: one false accept in a hundred pairs
    license: str
    trained_on: str
    brand: str  # who published the model: the mark the admin shows for it


CATALOGUE: Mapping[str, Catalogued] = {
    "titanet-small": Catalogued(
        file="nemo_en_titanet_small.onnx",
        brand="nvidia",
        sha256="ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
        size=40257283,
        dimensions=192,
        threshold=0.45,
        license="NeMo toolkit licence (Apache-2.0), per NVIDIA NGC",
        trained_on="VoxCeleb, Fisher, Switchboard, LibriSpeech, NIST SRE",
    ),
    "3dspeaker-campplus-zh-en": Catalogued(
        file="3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
        brand="modelscope",
        sha256="aa3cfc16963a10586a9393f5035d6d6b57e98d358b347f80c2a30bf4f00ceba2",
        size=28281164,
        dimensions=192,
        threshold=0.51,
        license="Apache-2.0 (3D-Speaker)",
        trained_on="200k Chinese and English speakers",
    ),
    "3dspeaker-eres2net": Catalogued(
        file="3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx",
        brand="modelscope",
        sha256="c59158379255ad66e161679cca6af8d52d51e389e3224ab7d7a7baae295c2db5",
        size=26485263,
        dimensions=192,
        threshold=0.48,
        license="Apache-2.0 (3D-Speaker)",
        trained_on="VoxCeleb",
    ),
}


class SherpaOnnxSpeaker(SpeakerModel):
    """Contract: `start` fetches the model when it is not there yet and loads it; `embed` runs one stream per call
    in a worker thread, so turns may embed at once."""

    name = "sherpa-onnx"

    def __init__(
        self,
        *,
        model: str,
        data_dir: Path,
        threads: int = 1,
        threshold: float | None = None,
        release: str = RELEASE,
        provider: str = "sherpa-onnx-voice",
    ) -> None:
        self._model, self._threads, self._release, self._provider = model, threads, release, provider
        self._catalogued = CATALOGUE.get(model)
        self.brand = self._catalogued.brand if self._catalogued else "sherpa-onnx"
        if threshold is None:
            if self._catalogued is None:
                raise ContractError(f"{provider}: {model!r} is not in the catalogue, so it needs a `threshold`")
            threshold = self._catalogued.threshold
        self._threshold = threshold
        self._path = data_dir / FOLDER / self._catalogued.file if self._catalogued else Path(model)
        self._extractor: sherpa_onnx.SpeakerEmbeddingExtractor | None = None

    @property
    def space(self) -> VoiceSpace:
        if self._catalogued is not None:
            return VoiceSpace(model=self._model, dimensions=self._catalogued.dimensions)
        if self._extractor is None:
            raise ContractError(f"{self._provider}: the space of a model file is known once it is loaded")
        return VoiceSpace(model=self._path.name, dimensions=self._extractor.dim)

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def path(self) -> Path:
        """Where the model file is."""
        return self._path

    def details(self) -> Mapping[str, str]:
        return {"model": self._model, "threads": str(self._threads), "file": str(self._path)}

    async def start(self) -> None:
        if self._catalogued is not None:
            await self._fetch(self._catalogued)
        elif not self._path.is_file():
            raise ProviderError(self._provider, f"no model file at {self._path}", transient=False)
        self._extractor = await asyncio.to_thread(self._load)

    async def close(self) -> None:
        self._extractor = None

    def _load(self) -> "sherpa_onnx.SpeakerEmbeddingExtractor":
        import sherpa_onnx

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self._path), num_threads=self._threads)
        try:
            extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        except RuntimeError as error:
            raise ProviderError(self._provider, f"cannot load {self._path.name}: {error}", transient=False) from None
        if self._catalogued is not None and extractor.dim != self._catalogued.dimensions:
            raise ProviderError(self._provider, f"{self._path.name} gives {extractor.dim} dimensions", transient=False)
        return extractor

    async def _fetch(self, model: Catalogued) -> None:
        """Download the model once; a file that does not match its sha256 is never kept."""
        if self._path.is_file() and await asyncio.to_thread(_sha256, self._path) == model.sha256:
            return
        partial = self._path.with_name(f"{self._path.name}.part")
        partial.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        try:
            async with (
                httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60, connect=10)) as client,
                client.stream("GET", self._release + model.file) as response,
            ):
                if response.is_error:
                    raise ProviderError(self._provider, f"HTTP {response.status_code} for {model.file}", transient=True)
                with partial.open("wb") as out:
                    async for chunk in response.aiter_bytes():
                        digest.update(chunk)
                        out.write(chunk)
        except httpx.HTTPError as error:
            partial.unlink(missing_ok=True)
            raise ProviderError(self._provider, f"cannot download {model.file} ({error})", transient=True) from None
        except ProviderError:
            partial.unlink(missing_ok=True)
            raise
        if digest.hexdigest() != model.sha256:
            partial.unlink(missing_ok=True)
            raise ProviderError(self._provider, f"{model.file} does not match its sha256", transient=False)
        partial.replace(self._path)

    async def embed(self, audio: bytes) -> Vector:
        extractor = self._extractor
        if extractor is None:
            raise ContractError(f"{self._provider}: used before start()")
        return await asyncio.to_thread(self._embed, extractor, audio)

    def _embed(self, extractor: "sherpa_onnx.SpeakerEmbeddingExtractor", audio: bytes) -> Vector:
        stream = extractor.create_stream()
        stream.accept_waveform(self.sample_rate, [s / 32768.0 for s in samples(audio)])
        stream.input_finished()
        if not extractor.is_ready(stream):
            raise ProviderError(self._provider, "too little speech to tell a voice", transient=False)
        try:
            return tuple(extractor.compute(stream))
        except RuntimeError as error:
            raise ProviderError(self._provider, f"cannot compute a voiceprint: {error}", transient=False) from None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


class SherpaOnnxSpeakerSettings(AdapterSettings):
    """A voice model run by sherpa-onnx."""

    # a catalogue name, or an `.onnx` path; the admin shows the mark of whoever published a catalogue model
    model: str = Field(
        json_schema_extra={"examples": list(CATALOGUE), "brands": {name: m.brand for name, m in CATALOGUE.items()}}
    )
    # CPU threads of one voiceprint: a Raspberry Pi has 4 cores, and the voice pipeline needs the others
    threads: PositiveInt = Field(default=1, le=16, json_schema_extra={"advanced": True})
    # the similarity from which two voices are one: the catalogue's by default, required for a file of one's own
    threshold: float | None = Field(default=None, gt=0, lt=1, json_schema_extra={"advanced": True})

    @model_validator(mode="after")
    def _calibrated(self) -> Self:
        if self.model not in CATALOGUE and self.threshold is None:
            known = ", ".join(CATALOGUE)
            raise ValueError(f"{self.model!r} is not in the catalogue ({known}): give its `threshold`")
        return self


def build(settings: SherpaOnnxSpeakerSettings, name: str, services: Services) -> SherpaOnnxSpeaker:
    import sherpa_onnx  # noqa: F401 - the extra is checked when the configuration is built, not at the first turn

    return SherpaOnnxSpeaker(
        model=settings.model,
        data_dir=services.data_dir,
        threads=settings.threads,
        threshold=settings.threshold,
        provider=name,
    )


plugin = Plugin(
    Family.MODEL,
    "sherpa-onnx",
    SherpaOnnxSpeakerSettings,
    build,
    requires="nestor-home[voice-id]",
    serves=SpeakerModel,
)

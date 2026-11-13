"""Voiceprints with sherpa-onnx (`pip install 'nestor-home[voice-id]'`): a small speaker model run on the CPU, on
this machine, so no voice leaves the house.

`model` names one of the catalogue (`catalogue.py`), downloaded once from the sherpa-onnx releases into
`<data_dir>/models/voices/` and checked against its pinned sha256, or the path of an `.onnx` file of one's own
(any speaker model sherpa-onnx loads; its `threshold` must then be given, since nobody calibrated it).

Each catalogued model carries the threshold calibrated on the `speaker-id` bench: the similarity at which one
pair of different voices in a hundred is taken for the same. The WeSpeaker models of the same releases are left
out (sherpa-onnx does not take the mean off their features), and so is 3D-Speaker's English CAM++: they barely tell
voices apart (equal error rate 0.12 to 0.46 on the bench).
"""

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from nestor.adapters.models.sherpa_onnx.catalogue import SPEAKER_FOLDER, SPEAKER_RELEASE, SPEAKERS
from nestor.adapters.models.sherpa_onnx.releases import fetch
from nestor.core import ContractError, ProviderError
from nestor.modules.identity import SpeakerModel, Vector, VoiceSpace
from nestor.modules.identity.audio import samples

if TYPE_CHECKING:
    import sherpa_onnx


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
        release: str = SPEAKER_RELEASE,
        provider: str = "sherpa-onnx-speaker",
    ) -> None:
        self._model, self._threads, self._release, self._provider = model, threads, release, provider
        self._catalogued = SPEAKERS.get(model)
        self.brand = self._catalogued.brand if self._catalogued else "sherpa-onnx"
        if threshold is None:
            if self._catalogued is None:
                raise ContractError(f"{provider}: {model!r} is not in the catalogue, so it needs a `threshold`")
            threshold = self._catalogued.threshold
        self._threshold = threshold
        self._path = data_dir / SPEAKER_FOLDER / self._catalogued.file if self._catalogued else Path(model)
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
            await fetch(
                self._release + self._catalogued.file, self._path, self._catalogued.sha256, provider=self._provider
            )
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

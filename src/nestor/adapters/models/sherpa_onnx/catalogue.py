"""The models of the sherpa-onnx releases Nestor knows, where they are downloaded from and kept: speaker models with
the threshold the `speaker-id` bench calibrated, speech recognition models."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SPEAKER_RELEASE = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"  # their spelling
)
SPEAKER_FOLDER = Path("models") / "voices"  # under the data folder


@dataclass(frozen=True, slots=True, kw_only=True)
class CataloguedSpeaker:
    """A speaker model of the sherpa-onnx releases, with what the bench measured of it."""

    file: str
    sha256: str
    size: int  # bytes on disk
    dimensions: int
    threshold: float  # calibrated on the `speaker-id` bench: one false accept in a hundred pairs
    license: str
    trained_on: str
    brand: str  # who published the model: the mark the admin shows for it


SPEAKERS: Mapping[str, CataloguedSpeaker] = {
    "titanet-small": CataloguedSpeaker(
        file="nemo_en_titanet_small.onnx",
        brand="nvidia",
        sha256="ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
        size=40257283,
        dimensions=192,
        threshold=0.45,
        license="NeMo toolkit licence (Apache-2.0), per NVIDIA NGC",
        trained_on="VoxCeleb, Fisher, Switchboard, LibriSpeech, NIST SRE",
    ),
    "3dspeaker-campplus-zh-en": CataloguedSpeaker(
        file="3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
        brand="modelscope",
        sha256="aa3cfc16963a10586a9393f5035d6d6b57e98d358b347f80c2a30bf4f00ceba2",
        size=28281164,
        dimensions=192,
        threshold=0.51,
        license="Apache-2.0 (3D-Speaker)",
        trained_on="200k Chinese and English speakers",
    ),
    "3dspeaker-eres2net": CataloguedSpeaker(
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


TRANSCRIPTION_RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
TRANSCRIPTION_FOLDER = Path("models") / "speech"  # under the data folder


@dataclass(frozen=True, slots=True, kw_only=True)
class CataloguedTranscription:
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


TRANSCRIPTIONS: Mapping[str, CataloguedTranscription] = {
    "parakeet-v3": CataloguedTranscription(
        archive="sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2",
        sha256="1495e91b59d7fc53ddca91f3431758ec99f8fa253fdb0e1e851be0f72b14b0f9",  # 487 MB
        encoder="encoder.int8.onnx",
        decoder="decoder.int8.onnx",
        joiner="joiner.int8.onnx",
        kind="nemo_transducer",  # 25 European languages, found by itself; CC-BY-4.0 (NVIDIA)
        brand="nvidia",
    ),
}

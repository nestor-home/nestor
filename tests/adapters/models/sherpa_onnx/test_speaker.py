"""sherpa-onnx voices: settings, fetching a catalogued model once and only when it is the right file, errors as
`ProviderError`; plus, opt-in, the voice embedder contract on a real model and real voices."""

import hashlib
import io
import wave
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from nestor.adapters.models.sherpa_onnx.speaker import CATALOGUE, FOLDER, RELEASE, Catalogued, SherpaOnnxSpeaker, plugin
from nestor.core import ContractError, ProviderError
from nestor.core.i18n import Locale
from nestor.modules.identity import SpeakerModel
from nestor.runtime.plugins import Services
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.identity import SpeakerModelContract

NOT_A_MODEL = b"not an onnx model"
TINY = Catalogued(
    file="tiny.onnx",
    sha256=hashlib.sha256(NOT_A_MODEL).hexdigest(),
    size=len(NOT_A_MODEL),
    dimensions=3,
    threshold=0.42,
    license="test",
    trained_on="nothing",
    brand="nvidia",
)


def services(folder: Path) -> Services:
    return Services(data_dir=folder, localizer=EchoLocalizer(), locale=Locale("en"))


@pytest.fixture
def tiny(monkeypatch: pytest.MonkeyPatch) -> Catalogued:
    monkeypatch.setitem(CATALOGUE, "tiny", TINY)  # type: ignore[arg-type]
    return TINY


@pytest.fixture
def releases() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def test_a_catalogued_model_brings_its_space_and_calibrated_threshold(tmp_path: Path) -> None:
    voices = plugin.create({"model": "titanet-small"}, "voice", services(tmp_path))
    assert isinstance(voices, SherpaOnnxSpeaker)
    model = CATALOGUE["titanet-small"]
    assert voices.space.dimensions == model.dimensions and voices.space.model == "titanet-small"
    assert voices.threshold == model.threshold
    assert voices.path == tmp_path / FOLDER / model.file
    assert voices.details()["model"] == "titanet-small" and voices.details()["threads"] == "1"
    assert plugin.create({"model": "titanet-small", "threshold": 0.6}, "v", services(tmp_path)).threshold == 0.6


def test_a_model_file_of_ones_own_needs_its_threshold(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="threshold"):
        plugin.create({"model": str(tmp_path / "mine.onnx")}, "voice", services(tmp_path))
    with pytest.raises(ContractError, match="threshold"):
        SherpaOnnxSpeaker(model="mine.onnx", data_dir=tmp_path)
    with pytest.raises(ContractError, match="threads"):
        plugin.create({"model": "titanet-small", "threads": 0}, "voice", services(tmp_path))


async def test_a_model_file_that_is_missing_or_not_a_model_fails_to_start(tmp_path: Path) -> None:
    missing = SherpaOnnxSpeaker(model=str(tmp_path / "mine.onnx"), data_dir=tmp_path, threshold=0.5)
    with pytest.raises(ContractError, match="once it is loaded"):
        _ = missing.space
    with pytest.raises(ProviderError, match="no model file") as raised:
        await missing.start()
    assert not raised.value.transient
    (tmp_path / "mine.onnx").write_bytes(NOT_A_MODEL)
    with pytest.raises(ProviderError, match=r"cannot load mine\.onnx"):
        await missing.start()


async def test_a_voiceprint_before_start_is_a_mistake(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="before start"):
        await SherpaOnnxSpeaker(model="titanet-small", data_dir=tmp_path).embed(b"\0\0" * 16000)


async def test_a_catalogued_model_is_downloaded_once_and_checked(
    tmp_path: Path, tiny: Catalogued, releases: respx.MockRouter
) -> None:
    route = releases.get(RELEASE + tiny.file).respond(200, content=NOT_A_MODEL)
    voices = SherpaOnnxSpeaker(model="tiny", data_dir=tmp_path)
    with pytest.raises(ProviderError, match=r"cannot load tiny\.onnx"):  # the right file, but no real model
        await voices.start()
    assert (tmp_path / FOLDER / tiny.file).read_bytes() == NOT_A_MODEL
    with pytest.raises(ProviderError, match="cannot load"):
        await voices.start()
    assert route.call_count == 1  # kept: the second start did not download it again


async def test_a_download_that_does_not_match_its_sha256_is_never_kept(
    tmp_path: Path, tiny: Catalogued, releases: respx.MockRouter
) -> None:
    releases.get(RELEASE + tiny.file).respond(200, content=b"tampered")
    with pytest.raises(ProviderError, match="sha256") as raised:
        await SherpaOnnxSpeaker(model="tiny", data_dir=tmp_path).start()
    assert not raised.value.transient
    assert list((tmp_path / FOLDER).iterdir()) == []


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(404), httpx.ConnectError("offline")],
    ids=["not found", "offline"],
)
async def test_a_failed_download_is_a_transient_provider_error(
    tmp_path: Path, tiny: Catalogued, releases: respx.MockRouter, answer: httpx.Response | Exception
) -> None:
    route = releases.get(RELEASE + tiny.file)
    if isinstance(answer, Exception):
        route.mock(side_effect=answer)
    else:
        route.mock(return_value=answer)
    with pytest.raises(ProviderError) as raised:
        await SherpaOnnxSpeaker(model="tiny", data_dir=tmp_path).start()
    assert raised.value.transient
    assert list((tmp_path / FOLDER).iterdir()) == []


# --- live: a real model, real voices ------------------------------------------------------------------------

SAMPLES = {"a": ("fangjun-sr-1.wav", "fangjun-sr-2.wav"), "b": ("leijun-sr-1.wav", "leijun-sr-2.wav")}
CACHE = Path.home() / ".cache" / "nestor-tests"  # the model and recordings, kept between live runs


def _recording(name: str) -> bytes:
    """A recording of the sherpa-onnx release (16 kHz mono), as PCM."""
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(httpx.get(RELEASE + name, follow_redirects=True, timeout=60).raise_for_status().content)
    with wave.open(io.BytesIO(path.read_bytes())) as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (16000, 1, 2)
        return source.readframes(source.getnframes())


@pytest.mark.live
class TestSherpaOnnxVoiceLive(SpeakerModelContract):
    def embedder(self) -> SpeakerModel:
        return SherpaOnnxSpeaker(model="titanet-small", data_dir=CACHE)

    def speech(self, speaker: str, take: int) -> bytes:
        return _recording(SAMPLES[speaker][take])

    async def test_too_little_speech_is_a_provider_error_not_a_crash(self) -> None:
        async with self.embedder() as voices:
            vector = await voices.embed(self.speech("a", 0)[: 2 * 16000])
            assert len(vector) == voices.space.dimensions
            with pytest.raises(ProviderError):
                await voices.embed(b"")

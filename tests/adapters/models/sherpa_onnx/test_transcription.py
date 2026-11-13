"""Speech recognized locally by sherpa-onnx, without its model (half a gigabyte): a release unpacked inside its
folder only, a voice message decoded whatever its format, and each turn the voice pipeline cuts heard once."""

import io
import tarfile
from pathlib import Path

import pytest

from nestor.adapters.models.sherpa_onnx.releases import unpack
from nestor.adapters.models.sherpa_onnx.transcription import SherpaOnnxTranscription
from nestor.core import ContractError

av = pytest.importorskip("av", reason="the voice extra decodes recordings")
numpy = pytest.importorskip("numpy")


def release(path: Path, members: dict[str, bytes], *, link: str | None = None) -> Path:
    with tarfile.open(path, "w:bz2") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        if link is not None:
            info = tarfile.TarInfo("model/escape")
            info.type, info.linkname = tarfile.SYMTYPE, link
            tar.addfile(info)
    return path


def test_a_release_unpacks_inside_its_folder_once(tmp_path: Path) -> None:
    archive = release(tmp_path / "model.tar.bz2", {"model/tokens.txt": b"a 0\n"})
    unpack(archive, tmp_path / "models")
    assert (tmp_path / "models" / "model" / "tokens.txt").read_bytes() == b"a 0\n"
    archive.unlink()
    unpack(archive, tmp_path / "models")  # unpacked already: the archive, deleted since, is not needed again


@pytest.mark.parametrize(
    ("members", "link"),
    [({"../outside.txt": b"x"}, None), ({}, "/etc/passwd")],
    ids=["a-path-out-of-it", "a-link-out-of-it"],
)
def test_a_release_that_reaches_out_of_its_folder_is_refused(tmp_path: Path, members: dict, link: str | None) -> None:
    archive = release(tmp_path / "evil.tar.bz2", members, link=link)
    with pytest.raises(tarfile.TarError):
        unpack(archive, tmp_path / "models")
    assert not (tmp_path / "outside.txt").exists()


def ogg(seconds: float, rate: int = 48000) -> bytes:
    """An OGG/Opus recording of silence, as a messaging app sends a voice message."""
    out = io.BytesIO()
    with av.open(out, "w", format="ogg") as container:
        stream = container.add_stream("libopus", rate=rate)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(numpy.zeros((1, int(seconds * rate)), "int16"), layout="mono")
        frame.rate = rate
        for packet in (*stream.encode(frame), *stream.encode(None)):
            container.mux(packet)
    return out.getvalue()


class Heard(SherpaOnnxTranscription):
    """The adapter with its recognizer replaced by what it was given to hear: how many samples."""

    def __init__(self, tmp_path: Path) -> None:
        super().__init__(model="parakeet-v3", data_dir=tmp_path)
        self.heard: list[int] = []

    async def hear(self, samples: "numpy.ndarray") -> str:
        self.heard.append(len(samples))
        return "bonjour"


async def test_a_voice_message_is_decoded_to_the_rate_the_model_hears(tmp_path: Path) -> None:
    model = Heard(tmp_path)
    assert await model.transcribe(ogg(1.0), "audio/ogg") == "bonjour"
    [samples] = model.heard
    assert abs(samples - 16000) < 1600, "one second at 16 kHz, whatever the recording's own rate"


async def test_each_turn_the_pipeline_cuts_is_heard_once(tmp_path: Path) -> None:
    from pipecat.frames.frames import TranscriptionFrame

    model = Heard(tmp_path)
    service = model.stt()
    frames = [f async for f in service.run_stt(b"\x00\x00" * 8000)]
    assert [f.text for f in frames if isinstance(f, TranscriptionFrame)] == ["bonjour"]
    assert model.heard == [8000], "raw 16-bit PCM, not a WAV file"


def test_only_a_catalogued_model_is_known(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="parakeet-v3"):
        SherpaOnnxTranscription(model="whisper-huge", data_dir=tmp_path)

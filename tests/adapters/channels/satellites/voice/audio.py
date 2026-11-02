"""Speech to replay: real recordings (biometric data, kept outside git) and macOS `say`.

Turn taking is tested on recordings: a synthetic voice fools Smart Turn. Mechanisms (cutting off,
outages) are tested with `say`, offline and reproducible; its timings are an optimistic bound.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from .replay import Utterance

RECORDINGS = Path(
    os.environ.get("NESTOR_VOICE_RECORDINGS", Path(__file__).parents[5] / "poc" / "bench" / "audio" / "recordings")
)
SPEAKER = "mathis"
STREAM_POP_S = 0.1  # opening the microphone stream clicks for 20 to 40 ms at the start of each recording
SAY_RATE = 16000
SAY_CACHE = Path(tempfile.gettempdir()) / "nestor-voice-say"


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as file:
        return np.frombuffer(file.readframes(file.getnframes()), dtype=np.int16).copy(), file.getframerate()


@dataclass(frozen=True)
class Recording:
    text: str
    pcm: np.ndarray
    rate: int
    speech_start_s: float
    speech_end_s: float

    def at(self, t: float) -> tuple[Utterance, tuple[float, float]]:
        """The utterance played at `t`, and its speech span on the scenario clock."""
        return Utterance(t, self.pcm, self.rate), (t + self.speech_start_s, t + self.speech_end_s)


@cache
def _manifest() -> dict:
    path = RECORDINGS / SPEAKER / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def has_recordings(*ids: str) -> bool:
    return all(i in _manifest() and (RECORDINGS / SPEAKER / _manifest()[i]["file"]).exists() for i in ids)


def needs_recordings(*ids: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not has_recordings(*ids), reason=f"recordings absent from {RECORDINGS} (set NESTOR_VOICE_RECORDINGS)"
    )


needs_say = pytest.mark.skipif(shutil.which("say") is None, reason="macOS `say` voice required")


def recording(item_id: str) -> Recording:
    entry = _manifest()[item_id]
    pcm, rate = read_wav(RECORDINGS / SPEAKER / entry["file"])
    pcm[: int(STREAM_POP_S * rate)] = 0
    floor = _manifest().get("silence-piece", {}).get("rms_dbfs", -55.0)
    start, end = speech_span(pcm, rate, floor)
    return Recording(entry["text"], pcm, rate, start, end)


def speech_span(pcm: np.ndarray, rate: int, floor_dbfs: float, margin_db: float = 12.0) -> tuple[float, float]:
    """Start and end of speech: 20 ms frames above the room's noise floor (±0.3 s on a soft ending)."""
    frame = int(0.02 * rate)
    n = len(pcm) // frame
    x = pcm[: n * frame].astype(np.float64).reshape(n, frame) / 32768.0
    rms_db = 20 * np.log10(np.sqrt((x**2).mean(axis=1)) + 1e-12)
    loud = np.flatnonzero(rms_db > floor_dbfs + margin_db)
    return float(loud[0] * 0.02), float((loud[-1] + 1) * 0.02)


def say(at_s: float, text: str, voice: str = "Thomas") -> Utterance:
    """`text` spoken by macOS at `at_s`, 16 kHz, without the silence `say` adds around it."""
    SAY_CACHE.mkdir(parents=True, exist_ok=True)
    path = SAY_CACHE / f"{hashlib.sha1(f'{voice}|{text}'.encode()).hexdigest()[:16]}.wav"
    if not path.exists():
        subprocess.run(
            ["say", "-v", voice, "-o", str(path), "--file-format=WAVE", f"--data-format=LEI16@{SAY_RATE}", text],
            check=True,
        )
    pcm, _ = read_wav(path)
    loud = np.flatnonzero(np.abs(pcm) > 300)
    return Utterance(at_s, pcm[loud[0] : loud[-1] + 1], SAY_RATE)


def tone_wav(path: Path, seconds: float, rate: int = 24000) -> None:
    t = np.arange(int(rate * seconds)) / rate
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes((6000 * np.sin(2 * np.pi * 330 * t)).astype(np.int16).tobytes())

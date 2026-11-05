"""Plain helpers on 16-bit mono PCM and on voiceprints, in C-speed builtins (no array library in the core)."""

import math
import sys
from array import array

from nestor.modules.identity.types import Vector

FULL_SCALE = 32768.0
_CLIPPED = 32767


def samples(audio: bytes) -> array:
    """The samples of little-endian 16-bit PCM (a trailing odd byte is dropped)."""
    found = array("h")
    found.frombytes(audio[: len(audio) - len(audio) % 2])
    if sys.byteorder == "big":  # pragma: no cover - every supported platform is little-endian
        found.byteswap()
    return found


def duration_s(audio: bytes, sample_rate: int) -> float:
    return len(audio) // 2 / sample_rate


def level_dbfs(pcm: array) -> float:
    """Root mean square level, in decibels below full scale; minus infinity for silence."""
    if not pcm:
        return -math.inf
    rms = math.sqrt(math.sumprod(pcm, pcm) / len(pcm))
    return 20 * math.log10(rms / FULL_SCALE) if rms else -math.inf


def clipped(pcm: array) -> float:
    """The share of samples at full scale: the microphone saturated."""
    return (pcm.count(_CLIPPED) + pcm.count(-_CLIPPED - 1)) / len(pcm) if pcm else 0.0


def unit(vector: Vector | list[float]) -> Vector:
    norm = math.sqrt(math.sumprod(vector, vector))
    return tuple(v / norm for v in vector) if norm else tuple(vector)


def similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity of two unit vectors."""
    return math.sumprod(a, b)


def centroid(vectors: tuple[Vector, ...] | list[Vector]) -> Vector:
    """The unit mean of unit vectors: what they share."""
    return unit([math.fsum(values) for values in zip(*vectors, strict=True)])

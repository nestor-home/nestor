"""Phrases arrive as 16-bit mono WAV at 16 kHz (the browser resamples): their samples, or 400."""

import io
import wave

from nestor.admin.api.v1.errors import ApiError

RATE = 16000


def pcm(audio: bytes) -> bytes:
    """The samples of a 16-bit mono WAV at 16 kHz."""
    try:
        with wave.open(io.BytesIO(audio)) as found:
            if (found.getnchannels(), found.getsampwidth(), found.getframerate()) != (1, 2, RATE):
                raise ApiError(400, "audio_format")
            return found.readframes(found.getnframes())
    except (wave.Error, EOFError):
        raise ApiError(400, "audio_format") from None

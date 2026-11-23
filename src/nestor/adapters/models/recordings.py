"""What the speech adapters share about a recording: how long it lasts, which is what a transcription is billed by."""

import io
import logging

log = logging.getLogger("nestor.models")


def duration_s(audio: bytes) -> float | None:
    """How long a recording lasts, whatever its format, from its container or else its frames; `None` when it cannot
    be read (the transcription still runs: the provider may read what this cannot)."""
    import av  # the voice extra, that every speech adapter requires

    try:
        with av.open(io.BytesIO(audio), mode="r") as container:
            if container.duration:
                return container.duration / av.time_base
            stream = container.streams.audio[0]
            frames = container.decode(stream)
            seconds = sum(float(f.duration * f.time_base) for f in frames if f.duration and f.time_base)
            return seconds or None
    except (av.FFmpegError, ValueError, IndexError) as error:
        log.warning("cannot tell how long a recording lasts: %s", error)
        return None

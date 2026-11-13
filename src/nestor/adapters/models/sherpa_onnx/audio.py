"""Recordings (a voice message, OGG/Opus or any format FFmpeg reads) decoded by PyAV, which the voice extra installs,
to the samples a sherpa-onnx model hears."""

from typing import TYPE_CHECKING

from nestor.adapters.models.pipecat import SAMPLE_RATE
from nestor.core import ProviderError

if TYPE_CHECKING:
    import numpy


def decoded(audio: bytes, provider: str) -> "numpy.ndarray":
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

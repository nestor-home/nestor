"""A replay transport: plays utterances in real time and times what the speaker plays.

The input pushes 20 ms frames at the real pace (silence between utterances, like a microphone).
The output consumes audio at the real pace, like a speaker: otherwise a whole answer would be
"played" instantly and a barge-in would cut nothing.
"""

import asyncio
import time
from dataclasses import dataclass, field

import numpy as np
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams

FRAME_S = 0.02


@dataclass(frozen=True)
class Utterance:
    """16-bit mono PCM played `at_s` seconds after the scenario starts."""

    at_s: float
    pcm: np.ndarray
    sample_rate: int

    @property
    def end_s(self) -> float:
        return self.at_s + len(self.pcm) / self.sample_rate


@dataclass
class Playback:
    """What the speaker actually played, in seconds since the scenario started."""

    chunks: list[tuple[float, float]] = field(default_factory=list)

    def first_sound_after(self, t: float) -> float | None:
        return next((start for start, _ in self.chunks if start >= t), None)

    def sound_stops_after(self, t: float, min_gap_s: float = 2 * FRAME_S) -> float | None:
        """End of the sound playing at `t`: the first silence of at least `min_gap_s`."""
        end = None
        for start, stop in self.chunks:
            if stop <= t:
                continue
            if end is not None and start - end > min_gap_s:
                break
            end = stop
        return end


class ScenarioClock:
    def __init__(self) -> None:
        self._t0: float | None = None
        self.input_done = asyncio.Event()

    def start(self) -> None:
        self._t0 = time.monotonic()

    def now(self) -> float:
        return time.monotonic() - self._t0 if self._t0 is not None else 0.0

    async def sleep_until(self, t: float) -> None:
        if (delay := t - self.now()) > 0:
            await asyncio.sleep(delay)


class _ReplayInput(BaseInputTransport):
    def __init__(self, params: TransportParams, script: list[Utterance], clock: ScenarioClock) -> None:
        super().__init__(params)
        self._script = script
        self._clock = clock
        self._task: asyncio.Task[None] | None = None

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)
        self._task = self.create_task(self._play())

    async def cleanup(self) -> None:
        if self._task:
            await self.cancel_task(self._task)
        await super().cleanup()

    async def _play(self) -> None:
        rate = self.sample_rate
        timeline = _render(self._script, rate)
        step = int(rate * FRAME_S)
        self._clock.start()
        for i in range(0, len(timeline), step):
            await self._clock.sleep_until(i / rate)
            chunk = timeline[i : i + step]
            await self.push_audio_frame(InputAudioRawFrame(audio=chunk.tobytes(), sample_rate=rate, num_channels=1))
        self._clock.input_done.set()


class _CaptureOutput(BaseOutputTransport):
    def __init__(self, params: TransportParams, clock: ScenarioClock, playback: Playback) -> None:
        super().__init__(params)
        self._clock = clock
        self._playback = playback

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        duration = len(frame.audio) / (2 * frame.num_channels * frame.sample_rate)
        start = self._clock.now()
        if not _is_silent(frame.audio):
            self._playback.chunks.append((start, start + duration))
        await asyncio.sleep(duration)
        return True


class ReplayTransport(BaseTransport):
    def __init__(self, script: list[Utterance], *, tail_s: float = 6.0, in_rate: int = 16000) -> None:
        super().__init__()
        self.clock = ScenarioClock()
        self.playback = Playback()
        self.script = sorted(script, key=lambda u: u.at_s)
        # Final silence: time for the last answer to be produced and played.
        end = max((u.end_s for u in script), default=0.0) + tail_s
        timeline = [*self.script, Utterance(end, np.zeros(1, dtype=np.int16), in_rate)]
        params = TransportParams(
            audio_in_enabled=True, audio_out_enabled=True, audio_in_sample_rate=in_rate, audio_out_sample_rate=24000
        )
        self._input = _ReplayInput(params, timeline, self.clock)
        self._output = _CaptureOutput(params, self.clock, self.playback)

    def input(self) -> FrameProcessor:
        return self._input

    def output(self) -> FrameProcessor:
        return self._output


def _render(script: list[Utterance], rate: int) -> np.ndarray:
    total = max(u.end_s for u in script)
    out = np.zeros(int(total * rate) + 1, dtype=np.int32)
    for u in script:
        i = int(u.at_s * rate)
        out[i : i + len(u.pcm)] += u.pcm
    return np.clip(out, -32768, 32767).astype(np.int16)


def _is_silent(audio: bytes) -> bool:
    samples = np.frombuffer(audio, dtype=np.int16)
    return samples.size == 0 or int(np.abs(samples).max()) < 64

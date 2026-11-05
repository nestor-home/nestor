"""The voice listener: the speech of a turn goes to voice recognition as soon as the speaker stops, and the turn
gets what it told, without waiting more than it may."""

import asyncio
from dataclasses import dataclass

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    SystemFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import SleepFrame, run_test

from nestor.adapters.channels.satellites.voice.listener import VoiceListener
from nestor.core import PersonId
from nestor.modules.identity import Heard
from nestor.testing.channels import ScriptedAssistant

LEA = Heard(space="s", voiceprint=(1.0,), duration_s=1.0, person=PersonId("lea"), score=0.9, margin=0.8)
CHUNK = b"\x10\x00" * 320  # 20 ms at 16 kHz


@dataclass
class TurnComplete(SystemFrame):
    """The transcription is final: the bridge asks what the voice told."""


class Detector(FrameProcessor):
    """Stands for the speech detector downstream: it sends its findings back upstream, stamped when they pass."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStartedSpeakingFrame | VADUserStoppedSpeakingFrame | UserStartedSpeakingFrame):
            await self.push_frame(type(frame)(), FrameDirection.UPSTREAM)
            return
        await self.push_frame(frame, direction)


def speech(seconds: float) -> list[Frame]:
    chunks = [InputAudioRawFrame(audio=CHUNK, sample_rate=16000, num_channels=1) for _ in range(int(seconds * 50))]
    return [
        VADUserStartedSpeakingFrame(),
        *[f for c in chunks for f in (c, SleepFrame(0.02))],
        VADUserStoppedSpeakingFrame(),
    ]


async def heard_after(frames: list[Frame], assistant: ScriptedAssistant, wait_s: float = 0.5) -> Heard | None:
    listener = VoiceListener(assistant)
    found: list[Heard | None] = []

    class Turn(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)
            if isinstance(frame, TurnComplete):
                found.append(await listener.heard(wait_s))
            await self.push_frame(frame, direction)

    await run_test(
        Pipeline([listener, Detector(), Turn()]),
        frames_to_send=[*frames, SleepFrame(0.1), TurnComplete(), SleepFrame(0.6)],
    )
    return found[0]


async def test_the_speech_of_a_turn_is_heard_once_the_speaker_stops() -> None:
    assistant = ScriptedAssistant(lambda _: "", voice=LEA)
    heard = await heard_after(speech(0.4), assistant)
    assert heard == LEA
    assert len(assistant.heard[-1]) >= len(CHUNK) * 15, "most of the 0.4 s said"


async def test_an_acknowledgement_before_the_turn_is_not_part_of_it() -> None:
    assistant = ScriptedAssistant(lambda _: "", voice=LEA)
    await heard_after([*speech(0.2), UserStartedSpeakingFrame(), *speech(0.4)], assistant)
    assert len(assistant.heard[-1]) < len(CHUNK) * 30, "only the turn's own speech"


async def test_a_recognition_too_slow_is_not_waited_for() -> None:
    class Slow(ScriptedAssistant):
        async def hear(self, audio: bytes) -> Heard | None:
            await asyncio.sleep(1)
            return LEA

    assert await heard_after(speech(0.2), Slow(lambda _: "", voice=LEA), wait_s=0.05) is None


async def test_nothing_said_is_nothing_heard() -> None:
    assistant = ScriptedAssistant(lambda _: "", voice=LEA)
    assert await heard_after([], assistant) is None

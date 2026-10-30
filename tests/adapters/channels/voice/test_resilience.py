import logging
import wave
from pathlib import Path

import pytest
from pipecat.frames.frames import ErrorFrame, Frame, OutputAudioRawFrame, TTSSpeakFrame, UserStartedSpeakingFrame
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from nestor.adapters.channels.voice.resilience import Injector, Outage, SpeechFallbacks, load_clips

from .audio import tone_wav
from .doubles import ScriptedSTT
from .replay import ReplayTransport


def test_clips_are_loaded_by_outage_and_a_missing_one_is_reported(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tone_wav(tmp_path / "tts.wav", seconds=0.5)
    with caplog.at_level(logging.WARNING):
        clips = load_clips(tmp_path)
    assert set(clips) == {Outage.TTS}
    assert len(clips[Outage.TTS].audio) == 2 * 12000
    assert "stt outage" in caplog.text


def test_without_a_folder_every_clip_is_reported_missing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert load_clips(None) == {}
    assert "stt outage" in caplog.text and "tts outage" in caplog.text


def test_a_clip_that_is_not_16_bit_is_refused(tmp_path: Path) -> None:
    with wave.open(str(tmp_path / "stt.wav"), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(1)
        clip.setframerate(8000)
        clip.writeframes(bytes(800))
    with pytest.raises(ValueError, match="16-bit"):
        load_clips(tmp_path)


class _Recorder(Injector):
    def __init__(self) -> None:
        super().__init__()
        self.injected: list[Frame] = []

    async def inject(self, frame: Frame) -> None:
        self.injected.append(frame)


async def _push(fallbacks: SpeechFallbacks, frame: Frame) -> None:
    source = FrameProcessor()
    await fallbacks.on_push_frame(FramePushed(source, source, frame, FrameDirection.UPSTREAM, 0))


def _error_from(processor: FrameProcessor) -> ErrorFrame:
    error = ErrorFrame("unavailable")
    error.processor = processor
    return error


async def test_a_transcription_outage_is_announced_once_per_user_turn() -> None:
    say, play = _Recorder(), _Recorder()
    fallbacks = SpeechFallbacks(say, play, stt_phrase="Je t'entends mal.", clips={})
    stt = ScriptedSTT(ReplayTransport([]), [])
    for frame in (_error_from(stt), _error_from(stt), UserStartedSpeakingFrame(), _error_from(stt)):
        await _push(fallbacks, frame)
    assert [f.text for f in say.injected if isinstance(f, TTSSpeakFrame)] == ["Je t'entends mal."] * 2
    assert not play.injected


async def test_errors_from_other_parts_of_the_pipeline_are_not_speech_outages() -> None:
    say, play = _Recorder(), _Recorder()
    clips = {Outage.STT: OutputAudioRawFrame(bytes(480), 24000, 1)}
    fallbacks = SpeechFallbacks(say, play, stt_phrase="Je t'entends mal.", clips=clips)
    await _push(fallbacks, _error_from(FrameProcessor()))
    assert not (say.injected or play.injected)

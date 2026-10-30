"""One connected client: its own realtime pipeline from the microphone to the speaker.

transport in → STT → user turns (VAD, Smart Turn, backchannels) → assistant bridge
→ response watcher → say → TTS (eager flush) → play → transport out → played text
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from pipecat.frames.frames import OutputAudioRawFrame
from pipecat.observers.user_bot_latency_observer import LatencyBreakdown, UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner

from nestor.adapters.channels.voice.bridge import AssistantBridge, PlayedText
from nestor.adapters.channels.voice.eager import ResponseWatcher
from nestor.adapters.channels.voice.embodiment import Embodiment
from nestor.adapters.channels.voice.providers import IN_SAMPLE_RATE, Speech
from nestor.adapters.channels.voice.resilience import Injector, Outage, SpeechFallbacks
from nestor.adapters.channels.voice.turns import TurnSettings, user_turns
from nestor.modules.behavior import Body
from nestor.modules.channels import Address, Assistant, Sender

logger = logging.getLogger(__name__)

OUT_SAMPLE_RATE = 24000


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionSettings:
    turns: TurnSettings = field(default_factory=TurnSettings)
    stt_phrase: str  # said when the transcription fails (`voice-stt-down` in the household's language)
    clips: Mapping[Outage, OutputAudioRawFrame] = field(default_factory=dict)
    quiet_s: float = 0.5  # silence required before an unprompted message is spoken


class VoiceSession:
    """`run` lasts as long as the client; `stop` ends it from elsewhere (disconnection, closing)."""

    def __init__(
        self,
        transport: BaseTransport,
        *,
        speech: Speech,
        assistant: Assistant,
        address: Address,
        sender: Sender,
        settings: SessionSettings,
        body: Body | None = None,
        rtvi: bool = True,
    ) -> None:
        """`body` is animated in sync with the played audio; `rtvi` speaks the Pipecat client protocol
        on the data channel (the browser client needs it, satellites speak the Nestor protocol)."""
        self.address = address
        played = PlayedText()
        self._bridge = AssistantBridge(
            assistant, address=address, sender=sender, played=played, quiet_s=settings.quiet_s
        )
        say, play = Injector(name="say"), Injector(name="play")
        pipeline = Pipeline(
            [
                transport.input(),
                speech.stt(),
                user_turns(settings.turns),
                self._bridge,
                ResponseWatcher(),
                say,
                speech.tts(),
                play,
                transport.output(),
                played,
            ]
        )
        latency = UserBotLatencyObserver()
        latency.add_event_handler("on_latency_breakdown", self._log_latency)
        fallbacks = SpeechFallbacks(say, play, stt_phrase=settings.stt_phrase, clips=settings.clips)
        embodiment = [Embodiment(body, transport.output())] if body is not None else []
        self._worker = PipelineWorker(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=IN_SAMPLE_RATE, audio_out_sample_rate=OUT_SAMPLE_RATE, enable_metrics=True
            ),
            observers=[latency, fallbacks, *embodiment],
            idle_timeout_secs=None,
            enable_rtvi=rtvi,
        )
        self._runner = WorkerRunner(handle_sigint=False)

    async def run(self) -> None:
        await self._runner.add_workers(self._worker)
        await self._runner.run()

    async def stop(self) -> None:
        await self._runner.cancel()

    async def say(self, text: str) -> None:
        """Speak an unprompted message once nobody is speaking."""
        await self._bridge.announce(text)

    async def _log_latency(self, _observer: UserBotLatencyObserver, breakdown: LatencyBreakdown) -> None:
        logger.info("voice: turn latency in %s\n%s", self.address, "\n".join(breakdown.turn_contribution_lines()))

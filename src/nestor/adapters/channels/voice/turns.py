"""When does the user's turn start and end, and when does their speech cut the assistant off?

Measured on recordings (see the voice proof of concept): Silero VAD detects speech, Smart Turn v3
decides after each pause whether the sentence is complete, and gives the turn anyway after 1.5 s of
silence when it judges it incomplete (as many hesitations kept as with Pipecat's 3 s default, 1.5 s
faster). An acknowledgement ("mmh", "ouais", "d'accord") while the assistant speaks does not cut it
off; a real reply ("attends", "non", a question) does. VAD alone cannot tell them apart: the first
transcribed words, or speech that lasts, decide.
"""

import asyncio
import re
from dataclasses import dataclass

from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregator, LLMUserAggregatorParams
from pipecat.turns.types import ProcessFrameResult
from pipecat.turns.user_start.base_user_turn_start_strategy import BaseUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

# French acknowledgements; a word outside this set makes the speech a real turn.
BACKCHANNELS = frozenset(
    [
        "mmh",
        "mmm",
        "mm",
        "mhm",
        "hm",
        "hmm",
        "hum",
        "ouais",
        "ouai",
        "oui",
        "ok",
        "okay",
        "d'accord",
        "daccord",
        "ah",
        "oh",
        "bah",
        "ben",
        "euh",
        "voilà",
        "vois",
        "je",
        "exact",
        "exactement",
        "carrément",
        "super",
        "cool",
        "bon",
        "ouf",
    ]
)
_WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿœ']+")


def is_backchannel(text: str) -> bool:
    """True when every word is an acknowledgement; nothing heard is not one."""
    words = _WORD.findall(text.lower().replace("\u2019", "'"))
    return bool(words) and all(word in BACKCHANNELS for word in words)


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnSettings:
    """Turn detection tuning; the defaults are the measured ones."""

    vad_start_s: float = 0.15
    vad_stop_s: float = 0.2
    incomplete_stop_s: float = 1.5  # silence after which a turn Smart Turn judges incomplete is given anyway
    stop_timeout_s: float = 5.0  # a turn that no strategy ends is ended after this silence
    long_speech_s: float = 1.2  # speech this long over the assistant cuts it off, even mistranscribed


class BackchannelAwareStart(BaseUserTurnStartStrategy):
    """Starts the user's turn, and so cuts the assistant off, only for a real reply.

    - Assistant silent: the turn starts on voice activity, without waiting for a transcription.
    - Assistant speaking: it waits for a word that is not an acknowledgement, or for `long_speech_s`
      of continuous speech; an acknowledgement that ends is forgotten so it does not leak into the
      next message.
    """

    def __init__(self, *, long_speech_s: float = 1.2) -> None:
        super().__init__()
        self._long_speech_s = long_speech_s
        self._bot_speaking = False
        self._timer: asyncio.Task[None] | None = None

    async def handle_user_turn_started(self) -> None:
        self._cancel_timer()

    async def cleanup(self) -> None:
        self._cancel_timer()
        await super().cleanup()

    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
        elif isinstance(frame, VADUserStartedSpeakingFrame):
            if not self._bot_speaking:
                await self.trigger_user_turn_started()
                return ProcessFrameResult.STOP
            self._cancel_timer()
            self._timer = asyncio.create_task(self._interrupt_if_long())
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._cancel_timer()
        elif isinstance(frame, InterimTranscriptionFrame | TranscriptionFrame):
            heard = frame.text.strip()
            if heard and not (self._bot_speaking and is_backchannel(heard)):
                # Words while silent (very short speech, late VAD) or a real reply over the assistant.
                await self.trigger_user_turn_started()
                return ProcessFrameResult.STOP
            if self._bot_speaking and isinstance(frame, TranscriptionFrame):
                await self.trigger_reset_aggregation()
        return ProcessFrameResult.CONTINUE

    async def _interrupt_if_long(self) -> None:
        await asyncio.sleep(self._long_speech_s)
        self._timer = None
        await self.trigger_user_turn_started()

    def _cancel_timer(self) -> None:
        timer, self._timer = self._timer, None
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()


def user_turns(settings: TurnSettings) -> LLMUserAggregator:
    """The Pipecat user aggregator: it pushes one `LLMContextFrame` per finished user turn and
    broadcasts an interruption when a turn starts."""
    stop = TurnAnalyzerUserTurnStopStrategy(
        turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams(stop_secs=settings.incomplete_stop_s))
    )
    return LLMUserAggregator(
        LLMContext(),
        params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(start_secs=settings.vad_start_s, stop_secs=settings.vad_stop_s)
            ),
            user_turn_strategies=UserTurnStrategies(
                start=[BackchannelAwareStart(long_speech_s=settings.long_speech_s)], stop=[stop]
            ),
            user_turn_stop_timeout=settings.stop_timeout_s,
            # A turn without transcript has nothing to send to the assistant.
            empty_user_turn=None,
        ),
    )

"""Drives a `Body` from the conversation, at the pace of the audio actually played.

Text comes back out of the transport output only when it is played (the synthesis's word
timestamps, or the sentence once its audio is out): a `[laughs]` animates the body when the laugh
is heard, not when the agent writes it. Behaviour follows the turns: listening while the user
speaks, thinking until the answer starts, speaking, then idle.
"""

import re

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    TTSTextFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from nestor.modules.behavior import Behavior, Body, Expression

# The expression tags the ElevenLabs v3/v4 voices perform, and the intent each one stands for.
VOICE_TAGS = {
    "laughs": Expression.JOY,
    "sighs": Expression.SIGH,
    "thoughtful": Expression.THOUGHTFUL,
    "whispers": Expression.WHISPER,
    "excited": Expression.EXCITED,
    "clears throat": Expression.AHEM,
}
_TAG = re.compile(r"\[([a-z ]+)\]")


def expressions_in(text: str) -> list[Expression]:
    found = (" ".join(tag.split()) for tag in _TAG.findall(text.lower()))
    return [VOICE_TAGS[tag] for tag in found if tag in VOICE_TAGS]


def words_in(text: str) -> int:
    return len(_TAG.sub(" ", text).split())


class Embodiment(BaseObserver):
    """`output` is the transport output, behind which text means "just played"."""

    def __init__(self, body: Body, output: FrameProcessor) -> None:
        super().__init__()
        self._body = body
        self._output = output
        self._user_speaking = False
        self._partial = ""  # a tag split by word timestamps: "[clears" then "throat]"

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if isinstance(frame, TTSTextFrame):
            if data.source is self._output and data.direction is FrameDirection.DOWNSTREAM:
                self._played(frame.text)
            return
        if not data.first_push:
            return
        if isinstance(frame, UserStartedSpeakingFrame | InterruptionFrame):
            self._user_speaking = True
            self._partial = ""
            self._body.set_behavior(Behavior.LISTENING)
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._user_speaking = False
            self._body.set_behavior(Behavior.THINKING)
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._body.set_behavior(Behavior.SPEAKING)
        elif isinstance(frame, BotStoppedSpeakingFrame) and not self._user_speaking:
            self._body.set_behavior(Behavior.IDLE)  # cut off by the user: it keeps listening instead

    def _played(self, text: str) -> None:
        text = self._partial + text
        if text.count("[") > text.count("]"):
            self._partial = text + " "
            return
        self._partial = ""
        for expression in expressions_in(text):
            self._body.express(expression)
        for _ in range(words_in(text)):
            self._body.beat()

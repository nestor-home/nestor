"""Behaviors, expressions and the capabilities a body may declare."""

from enum import StrEnum

from nestor.core import Capability

HEAD_MOTION = Capability("motion.head")
EXPRESSION = Capability("expression.emotion")


class Behavior(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class Expression(StrEnum):
    JOY = "joy"
    SIGH = "sigh"
    THOUGHTFUL = "thoughtful"
    WHISPER = "whisper"
    EXCITED = "excited"
    AHEM = "ahem"

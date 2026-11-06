"""What a voice channel speaks through: models of `models`, chosen by the household like any other.

How they stream (a realtime pipeline, its frames and timings) is the voice adapter's business: an implementation
also gives that adapter what it runs. The core only knows that a model hears or speaks.
"""

from abc import ABC

from nestor.core import Component


class Transcriber(Component, ABC):
    """Turns a person's speech into text, as they speak."""


class Synthesizer(Component, ABC):
    """Gives the assistant its voice: turns what it says into speech, as it is written."""

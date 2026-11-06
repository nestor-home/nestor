"""Channels: voice, messaging and web entry points, all leading to the same assistant."""

from nestor.modules.channels.ports import Assistant, Channel, MessageEnd, Reply
from nestor.modules.channels.speech import Synthesizer, Transcriber
from nestor.modules.channels.types import Address, Exchange, InboundMessage, Media, Medium, Sender

__all__ = [
    "Address",
    "Assistant",
    "Channel",
    "Exchange",
    "InboundMessage",
    "Media",
    "Medium",
    "MessageEnd",
    "Reply",
    "Sender",
    "Synthesizer",
    "Transcriber",
]

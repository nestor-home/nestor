"""Channels: voice, messaging and web entry points, all leading to the same assistant."""

from nestor.modules.channels.ports import Assistant, Channel, MessageEnd, Reply, SpeechModel, TranscriptionModel
from nestor.modules.channels.types import (
    Address,
    Attachment,
    AttachmentKind,
    Exchange,
    InboundMessage,
    Medium,
    Sender,
)

__all__ = [
    "Address",
    "Assistant",
    "Attachment",
    "AttachmentKind",
    "Channel",
    "Exchange",
    "InboundMessage",
    "Medium",
    "MessageEnd",
    "Reply",
    "Sender",
    "SpeechModel",
    "TranscriptionModel",
]

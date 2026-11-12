"""Conversation: turns, replies and fallbacks, shared by every channel.

Every channel — realtime voice included — reaches the same assistant through
`nestor.modules.channels`, so voice and messaging share one assistant and one memory.
"""

from nestor.modules.conversation.attachments import Attachments
from nestor.modules.conversation.conversations import Conversations
from nestor.modules.conversation.events import (
    AnswerCut,
    AssistantTurn,
    FallbackSpoken,
    NotificationTurn,
    SpeakerDeclared,
    UserTurn,
)
from nestor.modules.conversation.persona import Instructions, Persona
from nestor.modules.conversation.ports import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.conversation.service import Agent, AgentSettings, ChannelProfile, LiveReplies, ModelChoice
from nestor.modules.conversation.speakers import Speakers
from nestor.modules.conversation.types import SILENT, About, Attached, FallbackReason, Notification, ReplyPhase, Source

__all__ = [
    "SILENT",
    "About",
    "Agent",
    "AgentSettings",
    "AnswerCut",
    "AssistantTurn",
    "Attached",
    "Attachments",
    "ChannelProfile",
    "ContextProvider",
    "Conversations",
    "FallbackReason",
    "FallbackSpoken",
    "Instructions",
    "Layer",
    "LiveReplies",
    "ModelChoice",
    "Notification",
    "NotificationTurn",
    "Persona",
    "ReplyPhase",
    "Sections",
    "Source",
    "SpeakerDeclared",
    "Speakers",
    "TurnContext",
    "UserTurn",
]

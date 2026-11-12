"""Conversation: turns, replies and fallbacks, shared by every channel.

Every channel — realtime voice included — reaches the same assistant through
`nestor.modules.channels`, so voice and messaging share one assistant and one memory.
"""

from nestor.modules.conversation.attachments import Attachments
from nestor.modules.conversation.conversations import Conversations
from nestor.modules.conversation.events import (
    AnswerCut,
    AnswerVoiced,
    AssistantTurn,
    ConversationTitled,
    FallbackSpoken,
    NotificationTurn,
    SpeakerDeclared,
    UserTurn,
)
from nestor.modules.conversation.mentions import Mentions
from nestor.modules.conversation.persona import Instructions, Persona
from nestor.modules.conversation.ports import (
    ContextProvider,
    DocumentReader,
    Layer,
    MentionSource,
    Sections,
    TurnContext,
)
from nestor.modules.conversation.service import Agent, AgentSettings, ChannelProfile, LiveReplies, ModelChoice
from nestor.modules.conversation.speakers import Speakers
from nestor.modules.conversation.titles import ConversationTitles
from nestor.modules.conversation.types import (
    SILENT,
    About,
    Attached,
    FallbackReason,
    Mentioned,
    MentionKind,
    Notification,
    ReplyPhase,
    Source,
)

__all__ = [
    "SILENT",
    "About",
    "Agent",
    "AgentSettings",
    "AnswerCut",
    "AnswerVoiced",
    "AssistantTurn",
    "Attached",
    "Attachments",
    "ChannelProfile",
    "ContextProvider",
    "ConversationTitled",
    "ConversationTitles",
    "Conversations",
    "DocumentReader",
    "FallbackReason",
    "FallbackSpoken",
    "Instructions",
    "Layer",
    "LiveReplies",
    "MentionKind",
    "MentionSource",
    "Mentioned",
    "Mentions",
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

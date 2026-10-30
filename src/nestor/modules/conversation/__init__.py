"""Conversation: turns, replies and fallbacks, shared by every channel.

Every channel — realtime voice included — reaches the same assistant through
`nestor.modules.channels`, so voice and messaging share one assistant and one memory.
"""

from nestor.modules.conversation.conversations import ENDS_AFTER_S, Conversations
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, FallbackSpoken, UserTurn
from nestor.modules.conversation.persona import Persona
from nestor.modules.conversation.ports import ContextProvider
from nestor.modules.conversation.service import Agent, AgentSettings, ChannelProfile, LiveReplies
from nestor.modules.conversation.types import FallbackReason, ReplyPhase

__all__ = [
    "ENDS_AFTER_S",
    "Agent",
    "AgentSettings",
    "AnswerCut",
    "AssistantTurn",
    "ChannelProfile",
    "ContextProvider",
    "Conversations",
    "FallbackReason",
    "FallbackSpoken",
    "LiveReplies",
    "Persona",
    "ReplyPhase",
    "UserTurn",
]

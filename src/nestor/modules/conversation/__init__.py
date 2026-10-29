"""Conversation: turns, replies and fallbacks, shared by every channel.

Every channel — realtime voice included — reaches the same assistant through
`nestor.modules.channels`, so voice and messaging share one assistant and one memory.
"""

from nestor.modules.conversation.events import AssistantTurn, FallbackSpoken, UserTurn
from nestor.modules.conversation.types import FallbackReason

__all__ = ["AssistantTurn", "FallbackReason", "FallbackSpoken", "UserTurn"]

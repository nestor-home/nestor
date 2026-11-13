"""OpenAI-compatible API channel: Nestor answers `POST /v1/chat/completions` like a model would, on its own port, so
that any client of that API talks to it: Open WebUI, LibreChat, Home Assistant through a conversation integration
that takes a base URL (Extended OpenAI Conversation), a script.

Each key belongs to an account of the household (`openai-api:<name>`). The client sends its whole history; Nestor
keeps its own conversation, one for each of the client's threads (told apart by their first message), so only the
last message the person wrote is a turn (its pictures included); the client's own instructions and tools are not
used. A client that sends only its latest message, without the history, starts a new conversation each time. The
answer streams (`stream: true`) or comes whole. Nestor cannot write to an API client by itself: what it brings
unprompted goes through the person's other channels.
"""

from nestor.adapters.channels.openai_api.settings import OpenAIApiSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "openai-api", OpenAIApiSettings, build)

__all__ = ["plugin"]

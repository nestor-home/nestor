"""Claude over Anthropic's Messages API, streamed (Server-Sent Events), with httpx: no vendor SDK.

What it adds to Claude through an OpenAI-compatible endpoint: the instructions' stable layers are system blocks marked
for the prompt cache (`cache_control`), and the conversation itself is cached up to its last message, so that each tool
round of a turn reads the turn so far from the cache; a PDF someone sent is read whole, its pages as Claude sees them,
not only its extracted text.

Claude thinks before answering. The reasoning that led to a tool call (its `thinking` blocks, signed) goes back
unchanged with the call for the rest of the turn, as Claude asks; the journal does not keep it, so a later turn
replays its history without it, which the API accepts.
"""

from nestor.adapters.models.anthropic.settings import AnthropicLanguageSettings, build_language
from nestor.modules.cognition import LanguageModel
from nestor.runtime.plugins import Family, Plugin

language = Plugin(Family.MODEL, "anthropic", AnthropicLanguageSettings, build_language, serves=LanguageModel)

__all__ = ["language"]

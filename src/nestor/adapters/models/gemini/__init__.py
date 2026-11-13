"""Gemini over Google's Gemini API (`streamGenerateContent`, Server-Sent Events), with httpx: no vendor SDK.

What it adds to Gemini through an OpenAI-compatible endpoint: a PDF someone sent is read whole, its pages as Gemini
sees them; tool schemas go as JSON Schema (`parametersJsonSchema`), not the OpenAPI subset; each tool call carries the
thought signature Gemini wants back with it within the turn. A reply Gemini stops for safety or recitation is a
`ProviderError`, not a silent end.

The prompt cache: Gemini caches a request's prefix by itself (implicit caching, since Gemini 2.5), and the
instructions go from the most stable layer to the least, so a request reuses the previous one's. Its explicit cache
(`cachedContents`) is not used: it is a resource to create, pay for by the hour and delete, which must hold the system
instruction and the tools together, and the household layer changes with every memory recorded.
"""

from nestor.adapters.models.gemini.settings import GeminiLanguageSettings, build_language
from nestor.modules.cognition import LanguageModel
from nestor.runtime.plugins import Family, Plugin

language = Plugin(Family.MODEL, "gemini", GeminiLanguageSettings, build_language, serves=LanguageModel)

__all__ = ["language"]

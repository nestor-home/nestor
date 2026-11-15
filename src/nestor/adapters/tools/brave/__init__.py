"""Brave Search as the household's web search: its own index, an API key from api-search.brave.com."""

from nestor.adapters.tools.brave.settings import BraveSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "brave", BraveSettings, build)

__all__ = ["plugin"]

"""Brave Search as the household's web search: its own index, an API key from api-search.brave.com."""

from nestor.adapters.tools.brave.settings import BraveSettings, build
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "brave",
    BraveSettings,
    build,
    card=Card(summary="Web search through Brave's own index.", docs="tools#search", needs=(Need.KEY,)),
)

__all__ = ["plugin"]

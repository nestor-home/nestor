"""Tavily as the household's web search: a search API made for agents, an API key from tavily.com."""

from nestor.adapters.tools.tavily.settings import TavilySettings, build
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "tavily",
    TavilySettings,
    build,
    card=Card(summary="Web search through Tavily.", docs="tools#search", needs=(Need.KEY,)),
)

__all__ = ["plugin"]

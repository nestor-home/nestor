"""SearXNG as the household's web search: a metasearch engine it hosts itself, no key, nothing sent to a search
company under its name. The instance must allow the JSON format (`search.formats: [html, json]` in its settings)."""

from nestor.adapters.tools.searxng.settings import SearxngSettings, build
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "searxng",
    SearxngSettings,
    build,
    card=Card(
        summary="Web search through a SearXNG instance the household runs.", docs="tools#search", needs=(Need.SERVER,)
    ),
)

__all__ = ["plugin"]

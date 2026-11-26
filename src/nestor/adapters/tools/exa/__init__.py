"""Exa as a web search engine: its public MCP server's `web_search_exa`, free with no key, or with an API key from
exa.ai for higher limits. With no key it is a free tier: it may be slow or limited at times.

    tools:
      - kind: exa
        api_key: ${EXA_API_KEY}   # optional

With a key, the server is called with `exaApiKey` in its address, as Exa documents it; that path has not been tried
with a real key yet.
"""

from nestor.adapters.tools.exa.settings import ExaSettings, build
from nestor.modules.system.selfmap import Card
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "exa",
    ExaSettings,
    build,
    card=Card(summary="Web search through Exa, free without a key.", docs="tools#search"),
)

__all__ = ["plugin"]

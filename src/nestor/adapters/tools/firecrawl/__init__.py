"""Firecrawl as a web search engine: its search API, free with no key, or with an API key from firecrawl.dev for
higher limits; `url` points to an instance of one's own. With no key it is a free tier: it may be slow or limited.

    tools:
      - kind: firecrawl
        api_key: ${FIRECRAWL_API_KEY}   # optional

With a key, the key goes as `Authorization: Bearer`; that path has not been tried with a real key yet.
"""

from nestor.adapters.tools.firecrawl.settings import FirecrawlSettings, build
from nestor.modules.system.selfmap import Card
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "firecrawl",
    FirecrawlSettings,
    build,
    card=Card(summary="Web search through Firecrawl, free without a key.", docs="tools#search"),
)

__all__ = ["plugin"]

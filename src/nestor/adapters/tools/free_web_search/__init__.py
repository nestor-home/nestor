"""A web search with no key, as Hermes does it: the free tiers of Exa, Parallel, Firecrawl and Keenable, taken in turn,
each search going on to the next one when a tier is busy, down or turns it away.

    tools:
      - kind: free-web-search
        engines: [exa, parallel, firecrawl, keenable]   # the default: drop one, or change the order

Exa and Parallel answer through their public MCP servers, Firecrawl and Keenable through their public APIs. They send
no user identifier: Parallel gets a random id per process, Keenable is told the calls come from Nestor. A free tier
may change or close: the agent is told the search runs on them, and that a key (`brave`, `tavily`) or one's own
`searxng` makes it reliable.
"""

from nestor.adapters.tools.free_web_search.settings import FreeWebSearchSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "free-web-search", FreeWebSearchSettings, build)

__all__ = ["plugin"]

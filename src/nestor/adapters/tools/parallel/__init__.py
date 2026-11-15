"""Parallel as a web search engine: its public MCP server's `web_search`, free with no key, or with an API key from
parallel.ai for higher limits. With no key it is a free tier: it may be slow or limited at times.

    tools:
      - kind: parallel
        api_key: ${PARALLEL_API_KEY}   # optional

A random id per process lets the free tier limit this client; it says nothing of the household. With a key, the key
goes as `Authorization: Bearer`, as Parallel documents it; that path has not been tried with a real key yet.
"""

from nestor.adapters.tools.parallel.settings import ParallelSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "parallel", ParallelSettings, build)

__all__ = ["plugin"]

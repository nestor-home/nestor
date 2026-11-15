"""Keenable as a web search engine: its public search, free with no key, or with an API key from keenable.ai for
higher limits. With no key it is a free tier: it may be slow or limited at times.

    tools:
      - kind: keenable
        api_key: ${KEENABLE_API_KEY}   # optional

Keenable asks every app to name itself (`X-Keenable-Title: nestor`). With a key, the search is `/v1/search` and the
key goes as `Authorization: Bearer`; that path has not been tried with a real key yet.
"""

from nestor.adapters.tools.keenable.settings import KeenableSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "keenable", KeenableSettings, build)

__all__ = ["plugin"]

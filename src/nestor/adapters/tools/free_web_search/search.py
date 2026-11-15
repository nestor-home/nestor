"""The free tiers, taken in turn: each search starts with the next one, and goes on to the others when it is limited,
down or refused."""

import logging
import random
from collections.abc import Sequence

from nestor.adapters.tools.free_web_search.engine import Engine, passes_on
from nestor.core import ProviderError
from nestor.modules.web import Found, WebSearch

log = logging.getLogger(__name__)

NOTE = (
    "Your web search goes through the free tiers of {engines}, with no key: a search may be slow, cut short or "
    "refused when they are busy. When a search fails or finds little, say so, and that an API key would make it "
    "reliable (a web search engine such as Brave or Tavily in the configuration)."
)


class FreeWebSearch(WebSearch):
    brand = "free-web-search"

    def __init__(self, engines: Sequence[Engine]) -> None:
        self._engines = tuple(engines)
        self._next = random.randrange(len(self._engines))  # several homes do not all start with the same one

    def notes(self) -> Sequence[str]:
        labels = [e.label for e in self._engines]
        named = labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"
        return (NOTE.format(engines=named),)

    def details(self) -> dict[str, str]:
        return {"engines": ", ".join(e.name for e in self._engines)}

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        start, self._next = self._next, (self._next + 1) % len(self._engines)
        order = self._engines[start:] + self._engines[:start]
        failures = []
        for engine in order:
            try:
                return await engine.search(query, limit=limit)
            except ProviderError as error:
                if not passes_on(error):
                    raise
                log.info("free web search: %s could not answer (%s), next one", engine.name, error)
                failures.append(f"{engine.name}: {error}")
        raise ProviderError(
            "free-web-search", f"every free tier is busy or refused it ({'; '.join(failures)})", transient=True
        )

    async def close(self) -> None:
        for engine in self._engines:
            await engine.aclose()

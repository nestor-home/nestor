"""The web search port: an engine that answers a query with pages. The household plugs one or several; the agent gets
one `web_search` tool over them (`WebSearchTools`)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from nestor.core import Component
from nestor.modules.web.types import Found


class WebSearch(Component, ABC):
    """Contract (checked by `nestor.testing.web.WebSearchContract`): `search` returns pages, the most relevant first,
    none for a query nothing matches (at most `limit`); an engine that cannot answer raises `ProviderError`.

    `free_tier`: it answers without a key, on a free tier that may be slow, limited or closed at times; an engine with
    a key, or one the household hosts, is not."""

    free_tier: bool = False

    @abstractmethod
    async def search(self, query: str, *, limit: int) -> Sequence[Found]: ...

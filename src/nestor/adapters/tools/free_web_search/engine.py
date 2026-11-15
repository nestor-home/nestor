"""One free tier the search goes through: an engine with no key, that may be slow, limited or refused."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from nestor.adapters.common.http import StatusError
from nestor.core import ProviderError
from nestor.modules.web import Found

EXCERPT = 1_500  # characters kept of what an engine quotes of a page: some quote whole tables
REFUSED = frozenset({401, 402, 403})  # a free tier that turned this client away, for now


class Engine(ABC):
    name: str  # the vendor, as configured and named to the agent: "exa"
    label: str  # as people know it: "Exa"

    @abstractmethod
    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        """Pages, the most relevant first; `ProviderError` when the free tier cannot answer."""

    @abstractmethod
    async def aclose(self) -> None: ...


def passes_on(error: ProviderError) -> bool:
    """Whether another free tier may answer what this one could not: it was limited, down or unreachable, or it turned
    this client away. A query it refused as such would be refused everywhere."""
    return error.transient or (isinstance(error, StatusError) and error.status in REFUSED)


def excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT else f"{text[:EXCERPT].rstrip()}…"

"""Where the agent reads Nestor's documentation."""

from abc import abstractmethod

from nestor.core import Component


class Documentation(Component):
    """Nestor's documentation, page by page, in Markdown. Contract: `page` returns the page with that slug (`tools`,
    `agent/memory`); `ProviderError` when it cannot be read now (offline, the site down, no such page)."""

    @abstractmethod
    async def page(self, slug: str) -> str: ...

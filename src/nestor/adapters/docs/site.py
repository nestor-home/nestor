"""The documentation on nestorhome.dev: each page in Markdown at `/docs/<slug>.md`, read through the public web client
(public addresses only), with a short timeout so that an offline Nestor answers from its map at once."""

from nestor.adapters.common.web import PublicWeb
from nestor.modules.system.selfmap import DOCS, Documentation

MARKDOWN = "text/markdown, text/plain;q=0.9"
MAX_BYTES = 500_000  # the longest page (the protocol) is under 100 KB


class SiteDocumentation(Documentation):
    """Pages are kept once read, for the life of the instance: the docs change with a release, which restarts it."""

    name = "documentation"

    def __init__(self, docs: str = DOCS, *, timeout_s: float = 5.0) -> None:
        self._docs = docs.rstrip("/")
        self._web = PublicWeb(accept=MARKDOWN, timeout_s=timeout_s, max_bytes=MAX_BYTES)
        self._pages: dict[str, str] = {}

    async def page(self, slug: str) -> str:
        if slug not in self._pages:
            fetched = await self._web.get(f"{self._docs}/{slug}.md")
            self._pages[slug] = fetched.body.decode(errors="replace")
        return self._pages[slug]

    async def close(self) -> None:
        await self._web.aclose()

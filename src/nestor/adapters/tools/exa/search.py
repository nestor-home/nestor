"""The engine: `web_search_exa`, which answers in blocks of `Title:`, `URL:`, `Published:` and `Highlights:` lines."""

import urllib.parse
from collections.abc import Sequence

from nestor.adapters.tools.public_mcp import PublicMcpServer
from nestor.modules.web import Found, WebSearch

URL = "https://mcp.exa.ai/mcp"
FIELDS = ("Title:", "URL:", "Published:", "Author:", "Highlights:")


class ExaSearch(WebSearch):
    brand = "exa"

    def __init__(self, url: str = URL, *, api_key: str | None = None) -> None:
        self.free_tier = api_key is None
        keyed = f"{url}?{urllib.parse.urlencode({'exaApiKey': api_key})}" if api_key else url
        self._server = PublicMcpServer("exa", keyed, secret=api_key, timeout_s=30.0)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        return pages(await self._server.call("web_search_exa", {"query": query, "numResults": limit}))

    async def close(self) -> None:
        await self._server.aclose()


def pages(text: str) -> list[Found]:
    found = []
    for block in text.split("\n---\n"):
        fields: dict[str, str] = {}
        highlights: list[str] = []
        current = ""
        for line in block.split("\n"):  # not splitlines: page text may hold U+2028 and the like
            label = next((f for f in FIELDS if line.startswith(f)), None)
            if label:
                current, fields[label] = label, line[len(label) :].strip()
            elif current == "Highlights:":
                highlights.append(line)
        if url := fields.get("URL:"):
            published = fields.get("Published:")
            found.append(
                Found(
                    title=fields.get("Title:") or url,
                    url=url,
                    snippet="\n".join(highlights).strip(),
                    published=published if published and published != "N/A" else None,
                )
            )
    return found

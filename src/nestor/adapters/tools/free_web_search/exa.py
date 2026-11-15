"""Exa's free tier: its public MCP server's `web_search_exa`, which answers in blocks of `Title:`, `URL:`,
`Published:` and `Highlights:` lines."""

from collections.abc import Sequence

from nestor.adapters.tools.free_web_search.engine import Engine, excerpt
from nestor.adapters.tools.free_web_search.mcp import McpServer
from nestor.modules.web import Found

URL = "https://mcp.exa.ai/mcp"
FIELDS = ("Title:", "URL:", "Published:", "Author:", "Highlights:")


class Exa(Engine):
    name, label = "exa", "Exa"

    def __init__(self, url: str = URL) -> None:
        self._server = McpServer("exa", url, timeout_s=30.0)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        return pages(await self._server.call("web_search_exa", {"query": query, "numResults": limit}))[:limit]

    async def aclose(self) -> None:
        await self._server.aclose()


def pages(text: str) -> list[Found]:
    found = []
    for block in text.split("\n---\n"):
        fields: dict[str, str] = {}
        highlights: list[str] = []
        current = ""
        for line in block.splitlines():
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
                    snippet=excerpt("\n".join(highlights)),
                    published=published if published and published != "N/A" else None,
                )
            )
    return found

"""Reading a web page for the agent (`read_page`): its title and the text of its content, a PDF's text, a text file
as it is. Only public addresses (`adapters/common/web.py`): a page never reaches the household's own network."""

from collections.abc import Mapping, Sequence

from pydantic import Field, PositiveFloat, PositiveInt

from nestor.adapters.common.web import PAGES, PublicWeb, WebError, readable
from nestor.adapters.documents import FileReader
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolOutput, ToolProvider
from nestor.modules.conversation import DocumentReader
from nestor.modules.web import UNTRUSTED
from nestor.runtime import Family, Plugin, Services
from nestor.runtime.plugins import AdapterSettings

READ = ToolSpec(
    "read_page",
    "Read a public web page by its address: its title and the text of its content (menus and banners left out), or "
    f"the text of a PDF. Long pages come back in parts, readable with read_result. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "the page's full address, https://…"}},
        "required": ["url"],
    },
)


class WebPages(ToolProvider):
    def __init__(self, reader: DocumentReader, *, timeout_s: float = 15.0, max_bytes: int = 5_000_000) -> None:
        self._reader, self._timeout_s = reader, timeout_s
        self._web = PublicWeb(accept=PAGES, timeout_s=timeout_s, max_bytes=max_bytes)

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=READ, run=self.read, risk=Risk.READ, timeout_s=self._timeout_s + 5.0),)

    async def close(self) -> None:
        await self._web.aclose()

    async def read(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ToolFailed("give the page's address")
        if "://" not in url:
            url = f"https://{url}"
        try:
            fetched = await self._web.get(url)
            page = await readable(fetched, self._reader)
        except WebError as error:
            raise ToolFailed(error.reason) from None
        if page.title:
            return {"url": fetched.url, "title": page.title, "text": page.text, "note": UNTRUSTED}
        return {"url": fetched.url, "text": page.text, "note": UNTRUSTED}


class WebPagesSettings(AdapterSettings):
    timeout_s: PositiveFloat = 15.0
    max_bytes: PositiveInt = Field(default=5_000_000, json_schema_extra={"advanced": True})


def build(settings: WebPagesSettings, name: str, services: Services) -> WebPages:
    pages = WebPages(FileReader(), timeout_s=settings.timeout_s, max_bytes=settings.max_bytes)
    pages.name = name
    return pages


plugin = Plugin(Family.TOOLS, "web-pages", WebPagesSettings, build)

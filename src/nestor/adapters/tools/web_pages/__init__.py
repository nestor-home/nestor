"""Reading a web page for the agent (`read_page`): its title and the text of its content, a PDF's text, a text file
as it is. Only public addresses (`adapters/common/web.py`): a page never reaches the household's own network."""

from nestor.adapters.tools.web_pages.settings import WebPagesSettings, build
from nestor.modules.system.selfmap import Card
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "web-pages",
    WebPagesSettings,
    build,
    card=Card(
        summary="Reads a public web page or a PDF at an address (read_page).", docs="tools#pages-places-and-journeys"
    ),
)

__all__ = ["plugin"]

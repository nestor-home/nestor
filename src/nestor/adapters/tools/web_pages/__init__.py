"""Reading a web page for the agent (`read_page`): its title and the text of its content, a PDF's text, a text file
as it is. Only public addresses (`adapters/common/web.py`): a page never reaches the household's own network."""

from nestor.adapters.tools.web_pages.settings import WebPagesSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "web-pages", WebPagesSettings, build)

__all__ = ["plugin"]

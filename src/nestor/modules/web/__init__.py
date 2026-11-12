"""The web, as the agent reads it: a search engine behind one `web_search` tool, whichever provider serves it."""

from nestor.modules.web.ports import WebSearch
from nestor.modules.web.types import UNTRUSTED, Found

__all__ = ["UNTRUSTED", "Found", "WebSearch"]

"""The web, as the agent reads it: the search engines the household plugged, behind one `web_search` tool."""

from nestor.modules.web.ports import WebSearch
from nestor.modules.web.service import WebSearchTools
from nestor.modules.web.types import UNTRUSTED, Found

__all__ = ["UNTRUSTED", "Found", "WebSearch", "WebSearchTools"]

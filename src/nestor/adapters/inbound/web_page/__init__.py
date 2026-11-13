"""Web pages watched for changes, as watch items of the kind `page`: "tell me when the lamp drops under 50 €",
"when the town hall posts the new opening hours".

Each page is read every `every_s` (an hour by default, never less than five minutes) the way `read_page` reads it:
public addresses only, the text of its content without menus and banners, a PDF by its text. A change of that text
is an item whose body shows what changed, line by line; whether the change is the one someone waits for is the
triage's to judge. The page's last text is kept across restarts, so a change made while Nestor was down comes
after it starts; versions between two checks are not seen. The first check only notes the page as it is.
"""

from nestor.adapters.inbound.web_page.settings import WebPageSettings, build
from nestor.adapters.inbound.web_page.source import PageSource
from nestor.runtime import Family, Plugin

__all__ = ["PageSource", "WebPageSettings", "build", "plugin"]

plugin = Plugin(Family.INBOUND, "web-page", WebPageSettings, build)

"""News feeds (RSS and Atom) as watch items of the kind `feed`: "tell me when Linux 7 is out", "when LWN writes about
sqlite".

Each feed is checked in turn every `every_s` (15 minutes by default, never less than a minute), with the `ETag` and
`Last-Modified` it last sent, so that an unchanged feed answers `304` without a body. An entry is new when its id
(guid, Atom id, else its link) was not seen before: every id the feed lists is kept across restarts, with the last
ids it dropped, so an entry comes once even when the feed reorders or republishes. The first check of a feed only
notes what is there.
Feeds on the household's own network are refused, as `read_page` refuses pages (`adapters/common/web.py`).
"""

from nestor.adapters.inbound.rss.settings import RssSettings, build
from nestor.adapters.inbound.rss.source import FeedSource
from nestor.runtime import Family, Plugin

__all__ = ["FeedSource", "RssSettings", "build", "plugin"]

plugin = Plugin(Family.INBOUND, "rss", RssSettings, build)

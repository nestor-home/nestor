"""Calendars and contacts over CalDAV and CardDAV (iCloud, Fastmail, Nextcloud…), connected from the admin with a
login and an app password. No configuration key."""

from nestor.adapters.connectors.dav.settings import DavSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["plugin"]

plugin = Plugin(Family.CONNECTOR, "dav", DavSettings, build)

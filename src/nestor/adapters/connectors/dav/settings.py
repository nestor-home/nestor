"""Settings and build of the CalDAV and CardDAV connector."""

from nestor.adapters.connectors.dav.connector import DavConnector
from nestor.runtime import AdapterSettings, Services


class DavSettings(AdapterSettings):
    pass


def build(settings: DavSettings, name: str, services: Services) -> DavConnector:
    connector = DavConnector()
    connector.name = name
    return connector

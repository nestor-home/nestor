"""Settings and build of the Google connector."""

from pydantic import PositiveFloat

from nestor.adapters.connectors.common.accounts import AccountSettings
from nestor.adapters.connectors.google.connector import GoogleConnector
from nestor.runtime import Services


class GoogleSettings(AccountSettings):
    poll_interval_s: PositiveFloat = 30.0


def build(settings: GoogleSettings, name: str, services: Services) -> GoogleConnector:
    connector = GoogleConnector(**settings.model_dump())
    connector.name = name
    return connector

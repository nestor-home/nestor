"""Settings and build of the Microsoft 365 connector."""

from nestor.adapters.connectors.common.accounts import AccountSettings
from nestor.adapters.connectors.microsoft.connector import MicrosoftConnector
from nestor.runtime import Services


class MicrosoftSettings(AccountSettings):
    pass


def build(settings: MicrosoftSettings, name: str, services: Services) -> MicrosoftConnector:
    connector = MicrosoftConnector(**settings.model_dump())
    connector.name = name
    return connector

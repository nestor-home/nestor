"""Google accounts (Gmail, read only) connected from the admin with the household's own OAuth client.

Configuration (family `connector`, kind `google`), every key optional:

    poll_interval_s: 30      # how often the inbox history is read for watches
    blocked_s: 600           # wait between tries while the account must be reconnected
    retry_initial_s: 1       # first backoff delay after an outage or a rate limit, doubled up to retry_max_s
    retry_max_s: 300
    body_chars: 20000        # cap of a body read by google_mail_read
    excerpt_chars: 2000      # cap of the body excerpt given to watches
"""

from pydantic import PositiveFloat, PositiveInt, model_validator

from nestor.adapters.connectors.google.connector import INFO, SCOPES, GoogleConnector
from nestor.adapters.connectors.google.inbound import Every, GmailInbound, Wakeup
from nestor.runtime import AdapterSettings, Family, Plugin, Services

__all__ = ["INFO", "SCOPES", "Every", "GmailInbound", "GoogleConnector", "GoogleSettings", "Wakeup", "plugin"]


class GoogleSettings(AdapterSettings):
    poll_interval_s: PositiveFloat = 30.0
    blocked_s: PositiveFloat = 600.0
    retry_initial_s: PositiveFloat = 1.0
    retry_max_s: PositiveFloat = 300.0
    body_chars: PositiveInt = 20_000
    excerpt_chars: PositiveInt = 2_000

    @model_validator(mode="after")
    def _consistent(self) -> "GoogleSettings":
        if self.retry_max_s < self.retry_initial_s:
            raise ValueError("retry_max_s must not be below retry_initial_s")
        return self


def build(settings: GoogleSettings, name: str, services: Services) -> GoogleConnector:
    connector = GoogleConnector(**settings.model_dump())
    connector.name = name
    return connector


plugin = Plugin(Family.CONNECTOR, "google", GoogleSettings, build)

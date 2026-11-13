"""Settings and build of the IMAP connector."""

from pydantic import PositiveFloat, PositiveInt, model_validator

from nestor.adapters.connectors.imap.connector import ImapConnector
from nestor.adapters.connectors.imap.inbound import ImapTiming
from nestor.runtime import AdapterSettings, Services


class ImapSettings(AdapterSettings):
    timeout_s: PositiveFloat = 30.0
    idle_s: PositiveFloat = 1500.0
    poll_s: PositiveFloat = 60.0
    fetch_bytes: PositiveInt = 1_000_000
    blocked_s: PositiveFloat = 600.0
    retry_initial_s: PositiveFloat = 1.0
    retry_max_s: PositiveFloat = 300.0
    body_chars: PositiveInt = 20_000
    excerpt_chars: PositiveInt = 2_000

    @model_validator(mode="after")
    def _consistent(self) -> "ImapSettings":
        if self.retry_max_s < self.retry_initial_s:
            raise ValueError("retry_max_s must not be below retry_initial_s")
        if self.idle_s > 29 * 60:
            raise ValueError("idle_s must stay under 29 minutes (1740 s): servers drop longer IDLE")
        return self


def build(settings: ImapSettings, name: str, services: Services) -> ImapConnector:
    connector = ImapConnector(
        timing=ImapTiming(
            timeout_s=settings.timeout_s,
            idle_s=settings.idle_s,
            poll_s=settings.poll_s,
            fetch_bytes=settings.fetch_bytes,
        ),
        blocked_s=settings.blocked_s,
        retry_initial_s=settings.retry_initial_s,
        retry_max_s=settings.retry_max_s,
        body_chars=settings.body_chars,
        excerpt_chars=settings.excerpt_chars,
    )
    connector.name = name
    return connector

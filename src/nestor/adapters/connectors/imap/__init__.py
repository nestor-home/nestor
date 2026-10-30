"""Mailboxes reached over IMAP with an application password, read only.

Configuration (family `connector`, kind `imap`), every key optional:

    timeout_s: 30            # every IMAP command
    idle_s: 1500             # IDLE renewed after this long (servers drop it after 29 minutes at most)
    poll_s: 60               # between checks when the server has no IDLE
    fetch_bytes: 1000000     # a message is read up to this size
    blocked_s: 600           # wait between tries while the credentials are refused
    retry_initial_s: 1       # first backoff delay after an outage, doubled up to retry_max_s
    retry_max_s: 300
    body_chars: 20000        # cap of a body read by imap_mail_read
    excerpt_chars: 2000      # cap of the body excerpt given to watches
"""

from pydantic import PositiveFloat, PositiveInt, model_validator

from nestor.adapters.connectors.imap.account import ImapAccount
from nestor.adapters.connectors.imap.aioimap import AioImapClient
from nestor.adapters.connectors.imap.client import Fetched, LoginRefused, MailboxClient, MailboxUnavailable, Selected
from nestor.adapters.connectors.imap.connector import INFO, ImapConnector
from nestor.adapters.connectors.imap.inbound import ImapInbound, ImapTiming
from nestor.runtime import AdapterSettings, Family, Plugin, Services

__all__ = [
    "INFO",
    "AioImapClient",
    "Fetched",
    "ImapAccount",
    "ImapConnector",
    "ImapInbound",
    "ImapSettings",
    "ImapTiming",
    "LoginRefused",
    "MailboxClient",
    "MailboxUnavailable",
    "Selected",
    "plugin",
]


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


plugin = Plugin(Family.CONNECTOR, "imap", ImapSettings, build)

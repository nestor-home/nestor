"""The email channel's settings, and how it is built from them."""

from typing import Self

from pydantic import Field, model_validator

from nestor.adapters.channels.email.channel import EmailChannel
from nestor.adapters.channels.email.smtp import Security
from nestor.adapters.channels.messaging import MessagingSettings
from nestor.adapters.connectors.imap import ImapAccount
from nestor.adapters.connectors.imap.account import LOOPBACK
from nestor.core import Component
from nestor.runtime.plugins import RequiredSecret, Services


class EmailSettings(MessagingSettings):
    address: str = Field(min_length=3)  # Nestor's own address, where members write
    username: str = Field(min_length=1)  # the mailbox's login, for IMAP and SMTP
    password: RequiredSecret  # an application password
    imap_host: str
    imap_port: int = Field(default=993, ge=1, le=65535)
    smtp_host: str
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_security: Security = Security.TLS
    folder: str = "INBOX"
    require_authenticated: bool = True  # only mail the receiving server authenticated (DMARC, DKIM and SPF)

    @model_validator(mode="after")
    def _clear_only_here(self) -> Self:
        if self.smtp_security is Security.NONE and self.smtp_host.lower() not in LOOPBACK:
            raise ValueError("smtp_security none sends the password in clear: only to a server on this machine")
        return self


def build(settings: EmailSettings, name: str, services: Services) -> Component:
    imap = ImapAccount.of(  # refuses what cannot work, and speaks TLS beyond this machine
        {
            "host": settings.imap_host,
            "port": str(settings.imap_port),
            "username": settings.username,
            "password": settings.password.get_secret_value(),
            "folder": settings.folder,
        }
    )
    return EmailChannel(
        name,
        address=settings.address,
        imap=imap,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_security=settings.smtp_security,
        require_authenticated=settings.require_authenticated,
        **settings.common(services),
    )

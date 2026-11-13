"""Sending a mail over SMTP, with the mailbox's own login."""

import smtplib
import ssl
from email.message import EmailMessage
from enum import StrEnum

from nestor.core import ProviderError

PROVIDER = "email"


class Security(StrEnum):
    TLS = "tls"  # implicit TLS (SMTPS, port 465)
    STARTTLS = "starttls"  # upgraded after connecting (port 587)
    NONE = "none"  # only to a server on this machine (a local bridge)


def send(
    message: EmailMessage,
    *,
    host: str,
    port: int,
    security: Security,
    username: str,
    password: str,
    timeout_s: float,
) -> None:
    """Blocking: run it in a thread."""
    try:
        if security is Security.TLS:
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout_s, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=timeout_s)
        with server:
            if security is Security.STARTTLS:
                server.starttls(context=ssl.create_default_context())
            server.login(username, password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as error:
        raise ProviderError(PROVIDER, f"SMTP refused the login: {error.smtp_code}", transient=False) from None
    except (smtplib.SMTPException, OSError) as error:
        raise ProviderError(PROVIDER, f"SMTP: {type(error).__name__} {error}", transient=True) from None

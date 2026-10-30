"""An IMAP account as the person typed it, and a session on its folder."""

import contextlib
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass

from nestor.adapters.connectors.imap.client import PROVIDER, MailboxClient, Selected
from nestor.core import ProviderError
from nestor.modules.connectors import Secrets

LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
STARTTLS_PORT = 143


@dataclass(frozen=True, slots=True, kw_only=True)
class ImapAccount:
    host: str
    port: int
    username: str
    password: str
    folder: str = "INBOX"
    tls: bool = True  # implicit TLS (IMAPS)

    @classmethod
    def of(cls, secrets: Secrets) -> "ImapAccount":
        """`ProviderError(transient=False)` when the settings cannot work: the person must change them."""
        host = secrets.get("host", "").strip()
        local = host.lower() in LOOPBACK  # a bridge on this machine (Proton Bridge…): no network to cross
        port = secrets.get("port", "").strip() or "993"
        if not host or not port.isdigit() or not 0 < int(port) < 65536:
            raise ProviderError(PROVIDER, "give the server name and a port number (usually 993)", transient=False)
        account = cls(
            host=host,
            port=int(port),
            username=secrets.get("username", "").strip(),
            password=secrets.get("password", ""),
            folder=secrets.get("folder", "").strip() or "INBOX",
            tls=not local,  # passwords never cross a network in clear
        )
        if account.port == STARTTLS_PORT and account.tls:
            raise ProviderError(PROVIDER, "port 143 needs STARTTLS, which is not supported: use 993", transient=False)
        return account


type ClientFactory = Callable[[ImapAccount, float], MailboxClient]  # account, timeout in seconds


@contextlib.asynccontextmanager
async def session(
    account: ImapAccount, factory: ClientFactory, timeout_s: float
) -> AsyncGenerator[tuple[MailboxClient, Selected]]:
    """A logged-in connection with the account's folder selected, logged out at the end whatever happens."""
    client = factory(account, timeout_s)
    try:
        await client.open()
        await client.login(account.username, account.password)
        selected = await client.select(account.folder)
        yield client, selected
    finally:
        await client.close()

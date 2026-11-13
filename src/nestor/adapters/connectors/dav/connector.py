"""The CalDAV and CardDAV connector: the calendars and contacts of an account on any server that speaks them (iCloud,
Fastmail, Nextcloud, Synology, Radicale…), reached with a login and an app password."""

import asyncio
from collections.abc import Sequence

import httpx

from nestor.adapters.connectors.common.tools import service
from nestor.adapters.connectors.dav import calendar, contacts
from nestor.adapters.connectors.dav.dav import Dav, DavAccount, new_client
from nestor.core import Component
from nestor.core.i18n import Message
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors import Access, AuthKind, Connection, Connector, ConnectorInfo, SecretField


def _field(name: str, *, secret: bool = False, default: str | None = None) -> SecretField:
    return SecretField(name=name, label=Message.of(f"connector-dav-field-{name}"), secret=secret, default=default)


INFO = ConnectorInfo(
    kind="dav",
    brand="dav",
    title=Message.of("connector-dav-title"),
    description=Message.of("connector-dav-description"),
    auth=AuthKind.SECRET,
    fields=(
        _field("server"),
        _field("contacts_server", default=""),
        _field("username"),
        _field("password", secret=True),
    ),
    setup=Message.of("connector-dav-setup"),
    services=(
        service("calendar", calendar.EVENTS, calendar.CREATE),
        service("contacts", contacts.SEARCH),
    ),
)


class DavConnector(Connector, Component):
    """One HTTP client for every account; each account's calendars and address books are found once."""

    name = "dav"
    brand = "dav"
    info = INFO

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._accounts: dict[tuple[str, str, str], Dav] = {}  # by servers and login: one per account

    async def close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    async def identify(self, connection: Connection, access: Access) -> str:
        """The login, once the server let it find its calendars or its contacts (a server may hold only one)."""
        account = DavAccount.of(await access.secrets())
        dav = self._dav_of(account)
        found = await asyncio.gather(dav.calendars(), dav.address_books(), return_exceptions=True)
        failures = [f for f in found if isinstance(f, BaseException)]
        if len(failures) == len(found):
            raise failures[0]
        return account.username

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        async def dav() -> Dav:
            return self._dav_of(DavAccount.of(await access.secrets()))  # new settings are found again

        return (
            *calendar.CalendarTools(connection.account, dav).tools(),
            *contacts.ContactTools(connection.account, dav).tools(),
        )

    def _dav_of(self, account: DavAccount) -> Dav:
        """The account's collections, found again when its settings or password changed."""
        key = (account.calendars, account.contacts, account.username)
        known = self._accounts.get(key)
        if known is None or known.account != account:
            if self._client is None:
                self._client = new_client(self._transport)
            known = self._accounts[key] = Dav(account, self._client)
        return known

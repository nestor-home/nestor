"""Connecting accounts from the admin: the provider's consent page, the relay, and reconnections.

Like Home Assistant's Application Credentials, the household registers its own OAuth client with each
provider. The provider sends the browser back to the admin's `/connections/callback` when the admin
is served over HTTPS or on this machine; otherwise to a public relay page (`relay_url`) that only
forwards the browser here. The relay learns where to forward from the `state` it receives —
`<state>.<base64url(callback)>` — and never sees a token: the code it forwards is worthless without
the PKCE verifier kept by Nestor.

A service authorised by discovery (a remote MCP server) registers a client sending people back to the
same address, and may need no consent at all: it is then connected at once.

A reconnection keeps the broken connection until the new one works (a refused consent loses
nothing), then forgets it without revoking: revoking could take the new grant down with it. It reuses
what was typed for the broken one (a server's address), unless typed again.
"""

import base64
import urllib.parse

from nestor.admin.auth import PendingFlows
from nestor.admin.settings import CALLBACK_PATH, AdminSettings
from nestor.core import PersonId
from nestor.modules.connectors import Connection, Connections, Connector, Secrets, Status


class Connecting:
    def __init__(self, connections: Connections, settings: AdminSettings, flows: PendingFlows) -> None:
        self.connections, self.settings, self.flows = connections, settings, flows

    async def begin(
        self,
        kind: str,
        owner: PersonId | None,
        *,
        base_url: str,
        account_id: str | None,
        replaces: Connection | None = None,
    ) -> str:
        """The provider URL to send the browser to (`ContractError` without a registered client)."""
        redirect_uri = self.settings.redirect_uri(base_url)
        url = await self.connections.begin(kind, owner, redirect_uri)
        return self._sent(url, kind, owner, base_url, account_id, replaces)

    async def discover(
        self,
        kind: str,
        owner: PersonId | None,
        values: Secrets,
        *,
        base_url: str,
        account_id: str | None,
        replaces: Connection | None = None,
    ) -> str | Connection:
        """For a service authorised by discovery: the URL to send the browser to, or the connection made at once."""
        redirect_uri = self.settings.redirect_uri(base_url)
        found = await self.connections.discover(kind, owner, redirect_uri, values)
        if isinstance(found, Connection):
            return await self.settled(found, replaces.id if replaces else None)
        return self._sent(found, kind, owner, base_url, account_id, replaces)

    async def typed(self, connector: Connector, values: Secrets, replaces: Connection | None) -> dict[str, str]:
        """The fields typed for a reconnection: a field not sent keeps its value, one sent empty is cleared, and a
        required one left empty keeps its value. Secrets go with where they are sent: when a required field changes
        (a server's address), nothing else is kept."""
        kept = dict(await self.connections.access(replaces).secrets()) if replaces else {}
        typed = {name: value.strip() for name, value in values.items()}
        required = [f.name for f in connector.info.fields if f.default is None]
        if any(typed.get(name) and typed[name] != kept.get(name) for name in required):
            return typed
        return {**kept, **{name: value for name, value in typed.items() if value or name not in required}}

    def _sent(
        self,
        url: str,
        kind: str,
        owner: PersonId | None,
        base_url: str,
        account_id: str | None,
        replaces: Connection | None,
    ) -> str:
        """Remembers the flow, and when the provider comes back through the relay, tells it where this admin is."""
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        issued = dict(query)["state"]
        self.flows.add(
            issued, kind=kind, owner=owner, account_id=account_id, replaces=replaces.id if replaces else None
        )
        callback = f"{base_url}{CALLBACK_PATH}"
        if self.settings.redirect_uri(base_url) != callback:
            target = base64.urlsafe_b64encode(callback.encode()).rstrip(b"=").decode()
            query = [(k, f"{v}.{target}" if k == "state" else v) for k, v in query]
            url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
        return url

    def replaced(self, kind: str, connection_id: str | None) -> Connection | None:
        """The broken connection being reconnected; a working one is never replaced."""
        connection = self.connections.connections.get(connection_id) if connection_id else None
        if connection is None or connection.kind != kind or connection.status is Status.CONNECTED:
            return None
        return connection

    async def settled(self, connection: Connection, replaces: str | None) -> Connection:
        """The new connection, with the settings of the one it replaces (which is then forgotten)."""
        old = self.connections.connections.get(replaces) if replaces else None
        if old is None:
            return connection
        await self.connections.disconnect(old.id, revoke=False)
        return await self.connections.configure(
            connection.id, disabled_tools=old.disabled_tools, confirm_writes=old.confirm_writes
        )

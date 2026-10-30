"""Connecting accounts from the admin: the provider's consent page, the relay, and reconnections.

Like Home Assistant's Application Credentials, the household registers its own OAuth client with each
provider. The provider sends the browser back to the admin's `/connections/callback` when the admin
is served over HTTPS or on this machine; otherwise to a public relay page (`relay_url`) that only
forwards the browser here. The relay learns where to forward from the `state` it receives —
`<state>.<base64url(callback)>` — and never sees a token: the code it forwards is worthless without
the PKCE verifier kept by Nestor.

A reconnection keeps the broken connection until the new one works (a refused consent loses
nothing), then forgets it without revoking: revoking could take the new grant down with it.
"""

import base64
import urllib.parse

from nestor.admin.auth import PendingFlows
from nestor.admin.settings import CALLBACK_PATH, AdminSettings
from nestor.core import PersonId
from nestor.modules.connectors import Connection, Connections, Status


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
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        issued = dict(query)["state"]
        self.flows.add(
            issued, kind=kind, owner=owner, account_id=account_id, replaces=replaces.id if replaces else None
        )
        callback = f"{base_url}{CALLBACK_PATH}"
        if redirect_uri != callback:  # through the relay: tell it where this admin is
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

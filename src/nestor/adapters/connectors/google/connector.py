"""The Google connector: Gmail first, read only (sending comes later, behind the person's confirmation)."""

from collections.abc import Sequence

import httpx

from nestor.adapters.connectors.common import Backoff
from nestor.adapters.connectors.google.api import GmailApi, new_client
from nestor.adapters.connectors.google.inbound import Every, GmailInbound
from nestor.adapters.connectors.google.tools import GmailTools
from nestor.core import Component, ProviderError
from nestor.core.i18n import Message
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors import Access, AuthKind, Connection, Connector, ConnectorInfo, OAuthSpec
from nestor.modules.initiative import InboundEventSource

SCOPES = ("openid", "email", "https://www.googleapis.com/auth/gmail.readonly")

INFO = ConnectorInfo(
    kind="google",
    brand="google",
    title=Message.of("connector-google-title"),
    description=Message.of("connector-google-description"),
    auth=AuthKind.OAUTH2,
    oauth=OAuthSpec(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        scopes=SCOPES,
        extra_authorize={"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
        client_credentials=True,
    ),
    setup=Message.of("connector-google-setup"),
    inbound=("mail",),
)


class GoogleConnector(Connector, Component):
    """Tools and `identify` share one HTTP client, opened on first use; each inbound feed has its own."""

    name = "google"
    brand = "google"
    info = INFO

    def __init__(
        self,
        *,
        poll_interval_s: float = 30.0,
        blocked_s: float = 600.0,
        retry_initial_s: float = 1.0,
        retry_max_s: float = 300.0,
        body_chars: int = 20_000,
        excerpt_chars: int = 2_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.poll_interval_s, self.blocked_s = poll_interval_s, blocked_s
        self.retry_initial_s, self.retry_max_s = retry_initial_s, retry_max_s
        self.body_chars, self.excerpt_chars = body_chars, excerpt_chars
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    async def identify(self, access: Access) -> str:
        email = (await self._api(access).profile()).email
        if not email:
            raise ProviderError("gmail", "the profile has no email address", transient=False)
        return email

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        return GmailTools(connection, lambda: self._api(access), body_chars=self.body_chars).tools()

    def inbound(self, connection: Connection, access: Access) -> InboundEventSource | None:
        return GmailInbound(
            connection,
            access,
            wakeup=Every(self.poll_interval_s),
            backoff=Backoff(self.retry_initial_s, self.retry_max_s),
            blocked_s=self.blocked_s,
            excerpt_chars=self.excerpt_chars,
            transport=self._transport,
        )

    def _api(self, access: Access) -> GmailApi:
        if self._client is None:
            self._client = new_client(self._transport)
        return GmailApi(access, self._client)

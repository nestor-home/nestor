"""The IMAP connector: any mailbox reachable with a login and an (application) password, read only."""

from collections.abc import Sequence

from nestor.adapters.connectors.common import Backoff
from nestor.adapters.connectors.imap.account import ClientFactory, ImapAccount, session
from nestor.adapters.connectors.imap.aioimap import AioImapClient
from nestor.adapters.connectors.imap.inbound import ImapInbound, ImapTiming
from nestor.adapters.connectors.imap.tools import ImapTools
from nestor.core import Component
from nestor.core.i18n import Message
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors import Access, AuthKind, Connection, Connector, ConnectorInfo, SecretField
from nestor.modules.initiative import InboundEventSource

INFO = ConnectorInfo(
    kind="imap",
    brand="imap",
    title=Message.of("connector-imap-title"),
    description=Message.of("connector-imap-description"),
    auth=AuthKind.SECRET,
    fields=(
        SecretField(name="host", label=Message.of("connector-imap-field-host"), secret=False),
        SecretField(name="port", label=Message.of("connector-imap-field-port"), secret=False, default="993"),
        SecretField(name="username", label=Message.of("connector-imap-field-username"), secret=False),
        SecretField(name="password", label=Message.of("connector-imap-field-password")),
        SecretField(name="folder", label=Message.of("connector-imap-field-folder"), secret=False, default="INBOX"),
    ),
    setup=Message.of("connector-imap-setup"),
    inbound=("mail",),
)


class ImapConnector(Connector, Component):
    """Each tool call opens its own short session; each inbound feed keeps one open (IDLE)."""

    name = "imap"
    brand = "imap"
    info = INFO

    def __init__(
        self,
        *,
        timing: ImapTiming | None = None,
        blocked_s: float = 600.0,
        retry_initial_s: float = 1.0,
        retry_max_s: float = 300.0,
        body_chars: int = 20_000,
        excerpt_chars: int = 2_000,
        factory: ClientFactory = AioImapClient,
    ) -> None:
        self.timing = timing or ImapTiming()
        self.blocked_s, self.retry_initial_s, self.retry_max_s = blocked_s, retry_initial_s, retry_max_s
        self.body_chars, self.excerpt_chars = body_chars, excerpt_chars
        self._factory = factory

    async def identify(self, access: Access) -> str:
        """The username, once the server accepted it (`ProviderError(transient=False)` when refused)."""
        account = ImapAccount.of(await access.secrets())
        async with session(account, self._factory, self.timing.timeout_s):
            return account.username

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        async def account() -> ImapAccount:
            return ImapAccount.of(await access.secrets())

        return ImapTools(
            connection,
            account,
            self._factory,
            timeout_s=self.timing.timeout_s,
            fetch_bytes=self.timing.fetch_bytes,
            body_chars=self.body_chars,
        ).tools()

    def inbound(self, connection: Connection, access: Access) -> InboundEventSource | None:
        return ImapInbound(
            connection,
            access,
            self._factory,
            timing=self.timing,
            backoff=Backoff(self.retry_initial_s, self.retry_max_s),
            blocked_s=self.blocked_s,
            excerpt_chars=self.excerpt_chars,
        )

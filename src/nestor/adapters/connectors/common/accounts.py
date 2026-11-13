"""What the connectors of a cloud account (Google, Microsoft) share: their settings, one HTTP client for the tools,
an inbound feed of new mail paced the same way, and the facts learnt about each account while Nestor runs."""

from collections.abc import Callable
from typing import Self

import httpx
from pydantic import PositiveFloat, PositiveInt, model_validator

from nestor.adapters.connectors.common.retry import Backoff, Every
from nestor.adapters.documents import FileReader
from nestor.core import Component
from nestor.modules.connectors import Access, Connection, Connector
from nestor.modules.initiative import InboundEventSource
from nestor.runtime import AdapterSettings


class AccountSettings(AdapterSettings):
    poll_interval_s: PositiveFloat = 60.0  # how often the inbox is read for watches
    blocked_s: PositiveFloat = 600.0  # wait between tries while the account must be reconnected
    retry_initial_s: PositiveFloat = 1.0  # first backoff delay, doubled up to retry_max_s
    retry_max_s: PositiveFloat = 300.0
    body_chars: PositiveInt = 20_000  # cap of a mail or a file read
    excerpt_chars: PositiveInt = 2_000  # cap of the body excerpt given to watches
    file_bytes: PositiveInt = 20_000_000  # the largest file read

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.retry_max_s < self.retry_initial_s:
            raise ValueError("retry_max_s must not be below retry_initial_s")
        return self


class AccountConnector(Connector, Component):
    """Tools and `identify` share one HTTP client (`new_client`), opened on first use; each inbound feed (`feed`) has
    its own. `known` keeps, by account, what does not change between calls (a time zone, a list's id)."""

    feed: Callable[..., InboundEventSource]
    new_client: Callable[[httpx.AsyncBaseTransport | None], httpx.AsyncClient]

    def __init__(
        self,
        *,
        poll_interval_s: float = 60.0,
        blocked_s: float = 600.0,
        retry_initial_s: float = 1.0,
        retry_max_s: float = 300.0,
        body_chars: int = 20_000,
        excerpt_chars: int = 2_000,
        file_bytes: int = 20_000_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.poll_interval_s, self.blocked_s = poll_interval_s, blocked_s
        self.retry_initial_s, self.retry_max_s = retry_initial_s, retry_max_s
        self.body_chars, self.excerpt_chars, self.file_bytes = body_chars, excerpt_chars, file_bytes
        self.reader = FileReader()
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._known: dict[str, dict[str, str]] = {}

    async def close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    def inbound(self, connection: Connection, access: Access) -> InboundEventSource | None:
        return type(self).feed(
            connection,
            access,
            wakeup=Every(self.poll_interval_s),
            backoff=Backoff(self.retry_initial_s, self.retry_max_s),
            blocked_s=self.blocked_s,
            excerpt_chars=self.excerpt_chars,
            transport=self._transport,
        )

    def known(self, connection: Connection) -> dict[str, str]:
        return self._known.setdefault(connection.account, {})

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = type(self).new_client(self._transport)
        return self._client

"""New Outlook inbox messages as watch items, read by when they were received.

Cursor (kept in the connection's `Access` state): the reception time of the last message yielded, plus the ids
yielded at or after it (bounded), so that messages received in the same second are neither repeated nor skipped, and
a feed stopped in the middle of a batch resumes with the next one. The first start draws the line at that moment:
nothing older is yielded. A message moved out of the inbox before it is read is skipped.
"""

import logging
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from datetime import datetime

import httpx

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common import Backoff, Retry, Wakeup
from nestor.adapters.connectors.microsoft.graph import GraphApi, Json, new_client
from nestor.adapters.connectors.microsoft.mail import TEXT_BODY, address
from nestor.core import ProviderError, utc_now
from nestor.modules.connectors import Access, Connection
from nestor.modules.initiative import InboundEventSource, Incoming

log = logging.getLogger(__name__)

INBOX = "/me/mailFolders/inbox/messages"
PAGES = 20  # pages read past in one look, when they hold only mail already yielded
PAGE = 50
KEPT_IDS = 200


@dataclass(frozen=True, slots=True)
class ReceivedCursor:
    since: str  # the reception time (ISO 8601, UTC) from which messages are read
    delivered: tuple[str, ...] = ()  # ids already yielded among those received at `since`, most recent last

    @classmethod
    def of(cls, state: Mapping[str, str]) -> "ReceivedCursor | None":
        since = state.get("since")
        return cls(since, tuple(i for i in state.get("delivered", "").split(",") if i)) if since else None

    def state(self) -> dict[str, str]:
        return {"since": self.since, "delivered": ",".join(self.delivered)}

    def after(self, message_id: str, received: str) -> "ReceivedCursor":
        kept = self.delivered if received == self.since else ()
        return ReceivedCursor(received, (*kept, message_id)[-KEPT_IDS:])


class OutlookInbound(InboundEventSource):
    brand = "microsoft"  # Outlook has no mark of its own the admin can show
    kinds = ("mail",)

    def __init__(
        self,
        connection: Connection,
        access: Access,
        *,
        wakeup: Wakeup,
        backoff: Backoff | None = None,
        blocked_s: float = 600.0,
        excerpt_chars: int = 2000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = f"outlook-inbound:{connection.id}"
        self._connection, self._access, self._wakeup = connection, access, wakeup
        self._retry = Retry(self.name, backoff or Backoff(1.0, 300.0), blocked_s=blocked_s)
        self._excerpt_chars = excerpt_chars
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        await self._cursor()  # the first start draws the line: nothing older is yielded

    async def close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    async def items(self) -> AsyncGenerator[Incoming]:
        while True:
            cursor = await self._cursor()
            try:
                found = await self._received(cursor)
            except ProviderError as error:
                await self._retry.after(error)
                continue
            self._retry.succeeded()
            for message in found:
                received = str(message.get("receivedDateTime") or cursor.since)
                try:
                    yield self._incoming(message)
                finally:
                    cursor = cursor.after(str(message["id"]), received)
                    await self._access.save_state(cursor.state())
            await self._wakeup.wait()

    @property
    def _api(self) -> GraphApi:
        if self._client is None:
            self._client = new_client(self._transport)
        return GraphApi(self._access, self._client)

    async def _cursor(self) -> ReceivedCursor:
        cursor = ReceivedCursor.of(await self._access.load_state())
        if cursor is None:
            cursor = ReceivedCursor(utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"))
            await self._access.save_state(cursor.state())
            log.info("%s starts from %s: earlier mail is not yielded", self.name, cursor.since)
        return cursor

    async def _received(self, cursor: ReceivedCursor) -> list[Json]:
        """The inbox's messages received since the cursor and not yielded yet, oldest first, a page at a time: the next
        page comes at the next look, from the cursor moved past this one. Those of the cursor's second already yielded
        are left out by their id, never by their count (one archived meanwhile must not hide a new one): a page holding
        only those is read past, by Graph's own link to the next one."""
        params = [
            ("$filter", f"receivedDateTime ge {cursor.since}"),
            ("$orderby", "receivedDateTime asc"),
            ("$top", str(PAGE)),
            ("$select", "id,conversationId,from,subject,receivedDateTime,body"),
        ]
        url: str | None = INBOX
        for _ in range(PAGES):
            found = await self._api.get(url, params, TEXT_BODY)
            new = [
                m
                for m in found.get("value", [])
                if isinstance(m, dict) and m.get("id") and m["id"] not in cursor.delivered
            ]
            url, params = found.get("@odata.nextLink"), []  # the link carries its own query
            if new or not isinstance(url, str):
                return new
        return []

    def _incoming(self, message: Json) -> Incoming:
        received = str(message.get("receivedDateTime") or "")
        return Incoming(
            source=self._connection.id,
            kind="mail",
            title=str(message.get("subject") or ""),
            body=cap(str((message.get("body") or {}).get("content") or ""), self._excerpt_chars),
            sender=address(message.get("from")) or None,
            owner=self._connection.owner,
            data={"message_id": message["id"], "thread_id": message.get("conversationId")},
            at=datetime.fromisoformat(received) if received else utc_now(),
        )

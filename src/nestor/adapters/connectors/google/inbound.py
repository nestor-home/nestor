"""New Gmail inbox messages as watch items, from the mailbox history (users.history.list).

Cursor (kept in the connection's `Access` state): the history id up to which every added message was
yielded, plus the ids yielded since (bounded), so that a feed stopped in the middle of a batch resumes
without repeating or skipping one. The first start records the current history id and yields nothing
older. A history id Gmail no longer knows (404, after about a week offline) is replaced by the current
one: the mail received in between is not yielded, and a warning says so.

What makes the feed look again is a `Wakeup`: a fixed interval for now; a Pub/Sub watch can replace it
without touching the rest.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass

import httpx

from nestor.adapters.connectors.common import Backoff, Retry, cap
from nestor.adapters.connectors.google.api import GmailApi, GmailError, new_client
from nestor.adapters.connectors.google.mime import GmailMessage
from nestor.core import ProviderError, utc_now
from nestor.modules.connectors import Access, Connection
from nestor.modules.initiative import InboundEventSource, Incoming

log = logging.getLogger(__name__)

KEPT_IDS = 200


class Wakeup(ABC):
    """When to look for new mail again."""

    @abstractmethod
    async def wait(self) -> None: ...


class Every(Wakeup):
    def __init__(self, interval_s: float) -> None:
        self.interval_s = interval_s

    async def wait(self) -> None:
        await asyncio.sleep(self.interval_s)


@dataclass(frozen=True, slots=True)
class HistoryCursor:
    history_id: str
    delivered: tuple[str, ...] = ()  # message ids already yielded, most recent last

    @classmethod
    def of(cls, state: Mapping[str, str]) -> "HistoryCursor | None":
        history_id = state.get("history_id")
        if not history_id:
            return None
        return cls(history_id, tuple(i for i in state.get("delivered", "").split(",") if i))

    def state(self) -> dict[str, str]:
        return {"history_id": self.history_id, "delivered": ",".join(self.delivered)}

    def after(self, message_id: str) -> "HistoryCursor":
        return HistoryCursor(self.history_id, (*self.delivered, message_id)[-KEPT_IDS:])

    def advanced(self, history_id: str) -> "HistoryCursor":
        return HistoryCursor(history_id, self.delivered)


class GmailInbound(InboundEventSource):
    name = "gmail-inbound"
    brand = "gmail"
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
        self.name = f"gmail-inbound:{connection.id}"
        self._connection, self._access, self._wakeup = connection, access, wakeup
        self._retry = Retry(self.name, backoff or Backoff(1.0, 300.0), blocked_s=blocked_s)
        self._excerpt_chars = excerpt_chars
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        try:
            await self._cursor()  # the first start draws the line: nothing older is yielded
        except ProviderError as error:
            log.warning("%s could not read the mailbox yet (%s): retried when items are read", self.name, error)

    async def close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    async def items(self) -> AsyncGenerator[Incoming]:
        while True:
            try:
                cursor = await self._cursor()
                try:
                    added, latest = await self._added(cursor)
                except GmailError as error:
                    if error.status != 404:
                        raise
                    await self._resync(cursor)
                    await self._wakeup.wait()  # the new cursor is "now": nothing to read before the next look
                    continue
                found = [message for message_id in added if (message := await self._message(message_id))]
            except ProviderError as error:
                await self._retry.after(error)
                continue
            self._retry.succeeded()
            for message in found:
                try:
                    yield self._incoming(message)
                finally:
                    cursor = cursor.after(message.id)
                    await self._access.save_state(cursor.state())
            if latest != cursor.history_id:
                await self._access.save_state(cursor.advanced(latest).state())
            await self._wakeup.wait()

    @property
    def _api(self) -> GmailApi:
        if self._client is None:
            self._client = new_client(self._transport)
        return GmailApi(self._access, self._client)

    async def _cursor(self) -> HistoryCursor:
        cursor = HistoryCursor.of(await self._access.load_state())
        if cursor is None:
            cursor = HistoryCursor((await self._api.profile()).history_id)
            await self._access.save_state(cursor.state())
            log.info("%s starts from history id %s: earlier mail is not yielded", self.name, cursor.history_id)
        return cursor

    async def _added(self, cursor: HistoryCursor) -> tuple[list[str], str]:
        added: list[str] = []
        page: str | None = None
        while True:
            history = await self._api.history(cursor.history_id, page)
            added += [i for i in history.added if i not in added and i not in cursor.delivered]
            if history.next_page is None:
                return added, history.history_id
            page = history.next_page

    async def _message(self, message_id: str) -> GmailMessage | None:
        try:
            return GmailMessage.of(await self._api.message(message_id))
        except GmailError as error:
            if error.status != 404:
                raise
            return None  # deleted before we read it

    async def _resync(self, stale: HistoryCursor) -> None:
        current = (await self._api.profile()).history_id
        await self._access.save_state(HistoryCursor(current).state())
        log.warning(
            "%s: Gmail no longer knows history id %s; resuming from %s, mail received in between is not yielded",
            self.name,
            stale.history_id,
            current,
        )

    def _incoming(self, message: GmailMessage) -> Incoming:
        return Incoming(
            source=self._connection.id,
            kind="mail",
            title=message.subject,
            body=cap(message.text() or message.snippet, self._excerpt_chars),
            sender=message.header("from") or None,
            owner=self._connection.owner,
            data={"message_id": message.id, "thread_id": message.thread_id},
            at=message.received or utc_now(),
        )

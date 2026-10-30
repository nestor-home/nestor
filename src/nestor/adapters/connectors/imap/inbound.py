"""New messages of an IMAP folder as watch items.

Cursor (kept in the connection's `Access` state): the folder's UIDVALIDITY and the highest UID yielded.
New messages are those with a greater UID; the server is asked with `UID SEARCH UID n:*` (which always
returns the highest UID, even below n: it is filtered out). The first start, and a UIDVALIDITY change
(the folder was rebuilt: old UIDs mean nothing any more), take the folder's current end as the cursor
and yield nothing older. Between checks the connection waits in IDLE when the server offers it, polls
otherwise; any failure closes it and a new one is opened after a backoff.
"""

import logging
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass

from nestor.adapters.connectors.common import Backoff, Retry, cap
from nestor.adapters.connectors.imap.account import ClientFactory, ImapAccount, session
from nestor.adapters.connectors.imap.client import MailboxClient, Selected
from nestor.adapters.connectors.imap.message import MailMessage
from nestor.core import ProviderError, utc_now
from nestor.modules.connectors import Access, Connection
from nestor.modules.initiative import InboundEventSource, Incoming

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UidCursor:
    uidvalidity: int
    last_uid: int

    @classmethod
    def of(cls, state: Mapping[str, str]) -> "UidCursor | None":
        validity, last = state.get("uidvalidity", ""), state.get("last_uid", "")
        return cls(int(validity), int(last)) if validity.isdigit() and last.isdigit() else None

    def state(self) -> dict[str, str]:
        return {"uidvalidity": str(self.uidvalidity), "last_uid": str(self.last_uid)}


@dataclass(frozen=True, slots=True, kw_only=True)
class ImapTiming:
    timeout_s: float = 30.0  # every command
    idle_s: float = 25 * 60.0  # IDLE is renewed before servers drop it (RFC 2177: at most 29 minutes)
    poll_s: float = 60.0  # between checks when the server has no IDLE
    fetch_bytes: int = 1_000_000  # a message is fetched up to this size; attachments beyond are not needed


class ImapInbound(InboundEventSource):
    brand = "imap"
    kinds = ("mail",)

    def __init__(
        self,
        connection: Connection,
        access: Access,
        factory: ClientFactory,
        *,
        timing: ImapTiming | None = None,
        backoff: Backoff | None = None,
        blocked_s: float = 600.0,
        excerpt_chars: int = 2000,
    ) -> None:
        self.name = f"imap-inbound:{connection.id}"
        self._connection, self._access, self._factory = connection, access, factory
        self._timing = timing or ImapTiming()
        self._retry = Retry(self.name, backoff or Backoff(1.0, 300.0), blocked_s=blocked_s)
        self._excerpt_chars = excerpt_chars

    async def start(self) -> None:
        try:
            async with session(await self._account(), self._factory, self._timing.timeout_s) as (client, selected):
                await self._cursor(client, selected)  # the first start draws the line: nothing older is yielded
        except ProviderError as error:
            log.warning("%s could not read the mailbox yet (%s): retried when items are read", self.name, error)

    async def items(self) -> AsyncGenerator[Incoming]:
        while True:
            try:
                account = await self._account()
                async with session(account, self._factory, self._timing.timeout_s) as (client, selected):
                    cursor = await self._cursor(client, selected)
                    self._retry.succeeded()
                    while True:
                        for uid in await self._new(client, cursor):
                            message = await self._fetch(client, uid)
                            try:
                                if message is not None:  # None: expunged before it was fetched
                                    yield self._incoming(uid, message, account.folder)
                            finally:
                                cursor = UidCursor(cursor.uidvalidity, uid)
                                await self._access.save_state(cursor.state())
                        wait = self._timing.idle_s if client.supports_idle else self._timing.poll_s
                        await client.wait_for_change(wait)
            except ProviderError as error:
                await self._retry.after(error)

    async def _account(self) -> ImapAccount:
        return ImapAccount.of(await self._access.secrets())

    async def _cursor(self, client: MailboxClient, selected: Selected) -> UidCursor:
        cursor = UidCursor.of(await self._access.load_state())
        if cursor is not None and cursor.uidvalidity == selected.uidvalidity:
            return cursor
        known_end = selected.uidnext - 1 if selected.uidnext is not None else None
        last = known_end if known_end is not None else max(await client.search("ALL"), default=0)
        fresh = UidCursor(selected.uidvalidity, last)
        await self._access.save_state(fresh.state())
        if cursor is None:
            log.info("%s starts after UID %s: earlier mail is not yielded", self.name, last)
        else:
            log.warning(
                "%s: UIDVALIDITY changed (%s → %s), the folder was rebuilt; resuming after UID %s, "
                "mail received meanwhile may not be yielded",
                self.name,
                cursor.uidvalidity,
                selected.uidvalidity,
                last,
            )
        return fresh

    @staticmethod
    async def _new(client: MailboxClient, cursor: UidCursor) -> list[int]:
        """UIDs after the cursor, oldest first."""
        return sorted(u for u in await client.search("UID", f"{cursor.last_uid + 1}:*") if u > cursor.last_uid)

    async def _fetch(self, client: MailboxClient, uid: int) -> MailMessage | None:
        fetched = await client.fetch([uid], f"BODY.PEEK[]<0.{self._timing.fetch_bytes}>")
        return MailMessage.parse(fetched[0].data) if fetched else None

    def _incoming(self, uid: int, message: MailMessage, folder: str) -> Incoming:
        return Incoming(
            source=self._connection.id,
            kind="mail",
            title=message.subject,
            body=cap(message.body, self._excerpt_chars),
            sender=message.sender or None,
            owner=self._connection.owner,
            data={"uid": uid, "folder": folder},
            at=utc_now(),
        )

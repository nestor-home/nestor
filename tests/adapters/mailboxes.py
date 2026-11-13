"""A mailbox for the tests of what reads mail over IMAP (the IMAP connector, the email channel): its folder as the
server keeps it, and a client that reads it without a network."""

import asyncio
import contextlib
import re
from collections.abc import Sequence
from email import policy
from email.parser import BytesParser

from nestor.adapters.connectors.imap.account import ImapAccount
from nestor.adapters.connectors.imap.client import Fetched, LoginRefused, MailboxClient, MailboxUnavailable, Selected

PASSWORD = 'abcd "efgh" \\ijkl'  # an app password with characters IMAP must quote


class FakeMailbox:
    """The server side of one folder: UIDs, UIDVALIDITY, credentials, IDLE support, outages."""

    def __init__(self, *, idle: bool = True, uidnext: bool = True) -> None:
        self.idle, self.reports_uidnext = idle, uidnext
        self.uidvalidity = 1698000000
        self.next_uid = 1
        self.messages: dict[int, bytes] = {}
        self.username, self.password = "mathilde@free.fr", PASSWORD
        self.down = 0  # next connections refused
        self.drops = 0  # next waits for a change end with the connection dropped
        self.opened = 0
        self.connected = 0
        self.expunged_before_fetch: set[int] = set()  # deleted by another client between SEARCH and FETCH
        self.changed = asyncio.Event()

    def deliver(self, raw: bytes) -> int:
        uid, self.next_uid = self.next_uid, self.next_uid + 1
        self.messages[uid] = raw
        self.changed.set()
        return uid

    def rebuild(self) -> None:
        """The folder is recreated: new UIDVALIDITY, UIDs start over."""
        old = list(self.messages.values())
        self.uidvalidity += 1
        self.messages, self.next_uid = {}, 1
        for raw in old:
            self.deliver(raw)

    def search(self, criteria: Sequence[str]) -> list[int]:
        uids = sorted(self.messages)
        if criteria[:1] == ["UID"]:
            low = int(criteria[1].split(":")[0])
            found = [u for u in uids if u >= low]
            return found or uids[-1:]  # RFC 3501: n:* always contains the highest UID
        if criteria[:2] == ["OR", "SUBJECT"]:
            text = criteria[2].lower()
            return [u for u in uids if text in _decoded(self.messages[u]).lower()]
        return uids

    def section(self, uid: int, section: str) -> bytes:
        raw = self.messages[uid]
        if "HEADER.FIELDS" in section:
            return _headers(raw).encode() + b"\r\n"
        if limit := re.search(r"<0\.(\d+)>", section):
            return raw[: int(limit[1])]
        return raw


def _headers(raw: bytes) -> str:
    head = raw.split(b"\r\n\r\n", 1)[0].decode()
    return "\r\n".join(line for line in head.split("\r\n") if line.split(":")[0] in ("From", "Subject", "Date"))


def _decoded(raw: bytes) -> str:
    parsed = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    return f"{parsed['Subject']} {parsed['From']}"


class ScriptedClient(MailboxClient):
    def __init__(self, mailbox: FakeMailbox, account: ImapAccount) -> None:
        self.mailbox, self.account = mailbox, account
        self.open_ = False

    async def open(self) -> None:
        if self.mailbox.down:
            self.mailbox.down -= 1
            raise MailboxUnavailable("connection refused")
        self.mailbox.opened += 1
        self.mailbox.connected += 1
        self.open_ = True

    async def login(self, username: str, password: str) -> None:
        if (username, password) != (self.mailbox.username, self.mailbox.password):
            raise LoginRefused("[AUTHENTICATIONFAILED] Invalid credentials")

    async def select(self, folder: str) -> Selected:
        uidnext = self.mailbox.next_uid if self.mailbox.reports_uidnext else None
        return Selected(uidvalidity=self.mailbox.uidvalidity, uidnext=uidnext)

    async def search(self, *criteria: str, charset: str | None = None) -> list[int]:
        return self.mailbox.search([c.strip('"') for c in criteria])

    async def fetch(self, uids: Sequence[int], section: str) -> list[Fetched]:
        for uid in self.mailbox.expunged_before_fetch & set(uids):
            del self.mailbox.messages[uid]
        return [Fetched(u, self.mailbox.section(u, section)) for u in uids if u in self.mailbox.messages]

    @property
    def supports_idle(self) -> bool:
        return self.mailbox.idle

    async def wait_for_change(self, timeout_s: float) -> None:
        if self.mailbox.drops:
            self.mailbox.drops -= 1
            raise MailboxUnavailable("connection reset by peer")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.mailbox.changed.wait(), timeout_s)
        self.mailbox.changed.clear()

    async def close(self) -> None:
        if self.open_:
            self.mailbox.connected -= 1
            self.open_ = False

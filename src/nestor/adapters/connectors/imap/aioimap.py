"""`MailboxClient` over aioimaplib: implicit TLS (IMAPS), timeouts on every command, IDLE when offered.

aioimaplib hands back a response as its result (`OK`, `NO`, `BAD`) and lines: untagged data without
the leading `* `, literals as `bytearray`, the tagged status text last.
"""

import asyncio
import base64
import logging
import re
import ssl
from collections.abc import Awaitable, Coroutine, Sequence
from typing import Any

import aioimaplib

from nestor.adapters.connectors.imap.account import ImapAccount
from nestor.adapters.connectors.imap.client import Fetched, LoginRefused, MailboxClient, MailboxUnavailable, Selected

log = logging.getLogger(__name__)

_FETCH = re.compile(rb"^\d+ FETCH \(")
_UID = re.compile(rb"UID (\d+)")
_UIDVALIDITY = re.compile(rb"\[UIDVALIDITY (\d+)\]")
_UIDNEXT = re.compile(rb"\[UIDNEXT (\d+)\]")
_FAILURES = (aioimaplib.AioImapException, OSError, TimeoutError, asyncio.IncompleteReadError)

type Response = aioimaplib.Response


class AioImapClient(MailboxClient):
    def __init__(self, account: ImapAccount, timeout_s: float = 30.0) -> None:
        self._account, self._timeout_s = account, timeout_s
        self._imap: aioimaplib.IMAP4 | None = None
        self._lost = asyncio.Event()  # the server closed the connection
        self._greeted = False

    async def open(self) -> None:
        account = self._account
        tls: dict[str, Any] = {"ssl_context": ssl.create_default_context()} if account.tls else {}
        self._imap = aioimaplib.IMAP4(
            host=account.host, port=account.port, timeout=self._timeout_s, conn_lost_cb=self._on_lost, **tls
        )
        # Awaited from aside: a server that never answers CAPABILITY leaves aioimaplib's greeting holding a
        # lock its own timeout then waits for, forever.
        hello = asyncio.ensure_future(self._imap.wait_hello_from_server())
        try:
            done, _ = await asyncio.wait({hello}, timeout=self._timeout_s)
        finally:
            hello.cancel()
        error = hello.exception() if hello in done else TimeoutError()
        if error is not None:
            raise MailboxUnavailable(f"cannot reach {account.host}:{account.port} ({_describe(error)})")
        self._greeted = True

    def _on_lost(self, error: Exception | None) -> None:
        self._lost.set()

    async def login(self, username: str, password: str) -> None:
        response = await self._call(self._connected().login(username, password))
        if response.result != "OK":
            raise LoginRefused(f"{self._account.host} refused the login: {_text(response)}")

    async def select(self, folder: str) -> Selected:
        response = self._ok(await self._call(self._connected().select(_quoted(folder))), f"SELECT {folder}")
        validity = next((int(m[1]) for line in _data(response) if (m := _UIDVALIDITY.search(line))), None)
        if validity is None:
            raise MailboxUnavailable(f"{self._account.host} did not give the UIDVALIDITY of {folder}")
        uidnext = next((int(m[1]) for line in _data(response) if (m := _UIDNEXT.search(line))), None)
        return Selected(uidvalidity=validity, uidnext=uidnext)

    async def search(self, *criteria: str, charset: str | None = None) -> list[int]:
        response = self._ok(await self._call(self._connected().uid_search(*criteria, charset=charset)), "SEARCH")
        return [int(token) for line in _data(response) for token in line.split() if token.isdigit()]

    async def fetch(self, uids: Sequence[int], section: str) -> list[Fetched]:
        if not uids:
            return []
        uid_set = ",".join(map(str, uids))
        response = self._ok(await self._call(self._connected().uid("fetch", uid_set, f"(UID {section})")), "FETCH")
        found: list[Fetched] = []
        uid: int | None = None
        data = b""
        for line in response.lines[:-1]:
            if isinstance(line, bytearray):
                data = bytes(line)
                continue
            if _FETCH.match(line):
                if uid is not None:
                    found.append(Fetched(uid, data))
                uid, data = None, b""
            if match := _UID.search(line):
                uid = int(match[1])
        if uid is not None:
            found.append(Fetched(uid, data))
        return found

    @property
    def supports_idle(self) -> bool:
        return self._imap is not None and self._imap.has_capability("IDLE")

    async def wait_for_change(self, timeout_s: float) -> None:
        imap = self._connected()
        try:
            if not self.supports_idle:
                await self._unless_lost(asyncio.sleep(timeout_s), timeout_s)
                return
            idle = await asyncio.wait_for(imap.idle_start(timeout=timeout_s), self._timeout_s)
            await self._unless_lost(imap.wait_server_push(timeout=timeout_s), timeout_s + self._timeout_s)
            imap.idle_done()
            await asyncio.wait_for(idle, self._timeout_s)
        except _FAILURES as error:
            raise MailboxUnavailable(f"IDLE failed on {self._account.host} ({_describe(error)})") from None

    async def _unless_lost(self, waiting: Coroutine[object, object, object], timeout_s: float) -> None:
        """Wait for `waiting` (its own timeout is not a failure), failing as soon as the connection drops."""
        task, lost = asyncio.ensure_future(waiting), asyncio.ensure_future(self._lost.wait())
        try:
            done, _ = await asyncio.wait({task, lost}, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED)
        finally:
            task.cancel()
            lost.cancel()
        if lost in done:
            raise MailboxUnavailable(f"{self._account.host} closed the connection")
        if task in done:
            task.exception()  # retrieved and dropped: the wait timing out is the normal end of an IDLE

    async def close(self) -> None:
        imap, self._imap = self._imap, None
        if imap is None:
            return
        try:
            if imap.has_pending_idle():
                imap.idle_done()
            if self._greeted and not self._lost.is_set() and imap.get_state() != "LOGOUT":
                await asyncio.wait_for(imap.logout(), self._timeout_s)
        except (*_FAILURES, AttributeError) as error:
            log.debug("logout from %s failed: %s", self._account.host, _describe(error))
        finally:
            protocol = imap.protocol
            assert protocol is not None, "aioimaplib creates its protocol with the client"
            for task in list(protocol.tasks):  # a greeting still waiting for CAPABILITY
                task.cancel()
            if protocol.transport is not None:
                protocol.transport.close()

    def _connected(self) -> aioimaplib.IMAP4:
        if self._imap is None or self._lost.is_set():
            raise MailboxUnavailable(f"not connected to {self._account.host}")
        return self._imap

    async def _call(self, command: Awaitable[Response]) -> Response:
        try:
            return await asyncio.wait_for(command, self._timeout_s)
        except _FAILURES as error:
            raise MailboxUnavailable(f"{self._account.host}: {_describe(error)}") from None

    def _ok(self, response: Response, what: str) -> Response:
        if response.result != "OK":
            raise MailboxUnavailable(f"{self._account.host} refused {what}: {_text(response)}")
        return response


def _data(response: Response) -> list[bytes]:
    return [bytes(line) for line in response.lines[:-1] if isinstance(line, bytes)]


def _text(response: Response) -> str:
    last = response.lines[-1] if response.lines else b""
    return bytes(last).decode(errors="replace").strip() or response.result


def _quoted(folder: str) -> str:
    """A folder name as IMAP wants it: modified UTF-7 (RFC 3501 §5.1.3), quoted unless it is a plain atom."""
    encoded = re.sub(r"[^\x20-\x7e]+", _utf7, folder.replace("&", "&-"))
    if re.fullmatch(r"[A-Za-z0-9._/&+,-]+", encoded):
        return encoded
    return '"' + encoded.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _utf7(run: re.Match[str]) -> str:
    return "&" + base64.b64encode(run[0].encode("utf-16-be")).decode().rstrip("=").replace("/", ",") + "-"


def _describe(error: BaseException) -> str:
    return str(error) or type(error).__name__

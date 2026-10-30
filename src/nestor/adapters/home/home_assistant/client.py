"""A Home Assistant WebSocket API session: authentication, commands and one event subscription.

Protocol (https://developers.home-assistant.io/docs/api/websocket): the server opens with
`auth_required`, the client answers `auth` with a long-lived access token, the server replies
`auth_ok` or `auth_invalid`. Every later client message carries an increasing `id`; the server
answers it with a `result` of the same id (`success`, then `result` or `error`) and delivers the
events of a subscription as `event` messages carrying the subscription's id.
"""

import contextlib
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Generator
from typing import Any, Self
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from nestor.core import ContractError

MAX_MESSAGE_BYTES = 64 * 2**20  # `get_states` of a large installation exceeds websockets' 1 MiB default


class AuthenticationRejected(Exception):
    """Home Assistant refused the access token: retrying cannot help."""


class SessionLost(Exception):
    """The session could not be opened or broke: unreachable, closed, refused command, unexpected reply."""


def websocket_url(base_url: str) -> str:
    """`http(s)://host[:port][/prefix]` → `ws(s)://host[:port][/prefix]/api/websocket`."""
    parts = urlsplit(base_url)
    schemes = {"http": "ws", "https": "wss"}
    if parts.scheme not in schemes or not parts.netloc:
        raise ContractError(f"Home Assistant URL must be http(s)://host[:port], got {base_url!r}")
    path = parts.path.rstrip("/") + "/api/websocket"
    return urlunsplit((schemes[parts.scheme], parts.netloc, path, "", ""))


class _RedactAuth(logging.Filter):
    """websockets logs every frame at debug level, the `auth` frame and its token included (the
    logged frame is elided in the middle, but `access_token` always sits in its visible head)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if "access_token" in record.getMessage():
            record.msg, record.args = "> TEXT <auth message redacted>", None
        return True


_frames = logging.getLogger(f"{__name__}.websocket")
_frames.addFilter(_RedactAuth())


class HomeAssistantSession:
    """One authenticated connection. Commands run one at a time; events of the subscription that
    arrive while a command waits for its result are kept for `events()`, in order."""

    def __init__(self, connection: ClientConnection) -> None:
        self._connection = connection
        self._next_id = 1
        self._pending: deque[dict[str, Any]] = deque()

    @classmethod
    async def open(cls, url: str, token: str) -> Self:
        """Connects to `ws(s)://…/api/websocket` and authenticates. Raises `AuthenticationRejected`
        or `SessionLost`; the caller bounds the time it takes."""
        try:
            connection = await connect(url, max_size=MAX_MESSAGE_BYTES, open_timeout=None, logger=_frames)
        except (OSError, WebSocketException) as error:
            raise SessionLost(f"cannot connect: {_describe(error)}") from error
        session = cls(connection)
        try:
            await session._authenticate(token)
        except BaseException:
            await session.close()
            raise
        return session

    async def close(self) -> None:
        await self._connection.close()

    async def command(self, kind: str, **fields: Any) -> Any:
        """Sends one command and returns its `result`; a refusal is a `SessionLost`."""
        message_id = await self._send({"type": kind, **fields})
        while True:
            message = await self._receive()
            if message.get("type") == "result" and message.get("id") == message_id:
                if not message.get("success"):
                    raise SessionLost(f"{kind} refused: {message.get('error')}")
                return message.get("result")
            if message.get("type") == "event":
                self._pending.append(message)

    async def subscribe(self, event_type: str) -> None:
        await self.command("subscribe_events", event_type=event_type)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """The subscription's events (the `event` object of each message) until the connection breaks,
        which raises `SessionLost`."""
        while True:
            message = self._pending.popleft() if self._pending else await self._receive()
            if message.get("type") == "event":
                yield message.get("event") or {}

    async def _authenticate(self, token: str) -> None:
        if (await self._receive()).get("type") != "auth_required":
            raise SessionLost("the server did not ask for authentication: is it Home Assistant?")
        await self._send_raw({"type": "auth", "access_token": token})
        reply = await self._receive()
        match reply.get("type"):
            case "auth_ok":
                return
            case "auth_invalid":
                raise AuthenticationRejected(str(reply.get("message") or "access token refused"))
            case other:
                raise SessionLost(f"unexpected reply to authentication: {other!r}")

    async def _send(self, message: dict[str, Any]) -> int:
        message_id, self._next_id = self._next_id, self._next_id + 1
        await self._send_raw({"id": message_id, **message})
        return message_id

    async def _send_raw(self, message: dict[str, Any]) -> None:
        with _lost_on_error():
            await self._connection.send(json.dumps(message))

    async def _receive(self) -> dict[str, Any]:
        with _lost_on_error():
            raw = await self._connection.recv()
        try:
            message = json.loads(raw)
        except ValueError:
            raise SessionLost(f"not JSON: {str(raw)[:200]!r}") from None
        if not isinstance(message, dict):
            raise SessionLost(f"not a JSON object: {str(raw)[:200]!r}")
        return message


@contextlib.contextmanager
def _lost_on_error() -> Generator[None]:
    try:
        yield
    except WebSocketException as error:
        raise SessionLost(f"connection lost: {_describe(error)}") from error


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__} {error}".strip()

"""The MCP endpoint behind the executor's key: a request without a key that belongs to an executor is refused (401),
one over its rate held back (429), before the MCP app sees either; an admitted one carries its executor in its scope
(`SCOPE_KEY`), for `access` to read."""

import logging
import time
from collections import deque
from collections.abc import Callable, MutableMapping
from typing import Any

from mcp.server.streamable_http_manager import StreamableHTTPASGIApp

from nestor.mcp_server.access import SCOPE_KEY

log = logging.getLogger(__name__)

CALLS_PER_MINUTE = 120  # per key


class Rate:
    """Calls per executor over the last minute."""

    def __init__(self) -> None:
        self._calls: dict[str, deque[float]] = {}

    def allows(self, executor: str) -> bool:
        now, calls = time.monotonic(), self._calls.setdefault(executor, deque())
        while calls and now - calls[0] > 60:
            calls.popleft()
        if len(calls) >= CALLS_PER_MINUTE:
            log.warning("executor %s calls Nestor's MCP server too often", executor)
            return False
        calls.append(now)
        return True


class Guarded:
    def __init__(self, app: StreamableHTTPASGIApp, caller: Callable[[str], str | None]) -> None:
        """`caller`: the executor a key belongs to, `None` for a key that is no executor's."""
        self._app, self._caller, self._rate = app, caller, Rate()

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        headers = dict(scope.get("headers") or ())
        scheme, _, key = headers.get(b"authorization", b"").decode("latin-1").partition(" ")
        executor = self._caller(key.strip()) if scheme.lower() == "bearer" and key.strip() else None
        if executor is None:
            await _refuse(send, 401, b"unauthorized", (b"www-authenticate", b'Bearer realm="nestor"'))
            return
        if not self._rate.allows(executor):
            await _refuse(send, 429, b"too many calls", (b"retry-after", b"60"))
            return
        scope[SCOPE_KEY] = executor
        await self._app(scope, receive, send)


async def _refuse(send: Any, status: int, body: bytes, header: tuple[bytes, bytes]) -> None:
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"text/plain"), header]})
    await send({"type": "http.response.body", "body": body})

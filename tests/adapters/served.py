"""An ASGI app served over real HTTP on 127.0.0.1, for adapters that speak to a server (MCP servers…)."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import uvicorn

type Asgi = Callable[[dict[str, Any], Any, Any], Awaitable[None]]


class Served:
    """An ASGI app served over real HTTP on 127.0.0.1; stopping and starting again keeps the port.
    `app` builds a fresh application each time: an MCP session manager only runs once."""

    def __init__(self, app: Callable[[], Asgi]) -> None:
        self._app = app
        self.port = 0
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    def url(self, path: str = "/mcp") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app(), host="127.0.0.1", port=self.port, log_level="warning", timeout_graceful_shutdown=1
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            await asyncio.sleep(0.01)
        self.port = self._server.servers[0].sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None and self._task is not None:
            self._server.should_exit = True
            await self._task
            self._server = self._task = None


def bearer(app: Asgi, token: str) -> Asgi:
    """Refuses requests without the token, like Home Assistant's HTTP layer."""

    async def guarded(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and dict(scope["headers"]).get(b"authorization") != f"Bearer {token}".encode():
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"401: Unauthorized"})
            return
        await app(scope, receive, send)

    return guarded


async def eventually(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.02)

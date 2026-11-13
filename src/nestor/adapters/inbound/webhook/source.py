"""The webhook source: its server, the posts it accepted until they are taken."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from nestor.adapters.common.state import StateFile
from nestor.adapters.inbound.webhook.hooks import Hook, proven
from nestor.adapters.inbound.webhook.posts import EVENTS, incoming
from nestor.adapters.inbound.webhook.server import read_body
from nestor.core import new_id
from nestor.modules.initiative import InboundEventSource, Incoming
from nestor.runtime.server import EmbeddedServer

log = logging.getLogger(__name__)

PENDING = 1000  # posts accepted and not yet triaged; beyond, a sender is asked to retry later


class WebhookSource(InboundEventSource):
    brand = "webhook"

    def __init__(
        self,
        name: str,
        hooks: Sequence[Hook],
        state: StateFile,
        *,
        host: str = "127.0.0.1",
        port: int = 8474,
        max_bytes: int = 65_536,
    ) -> None:
        self.name = name
        self.kinds = tuple(dict.fromkeys(h.kind for h in hooks))
        self.follows = {kind: tuple(h.name for h in hooks if h.kind == kind) for kind in self.kinds}
        self._hooks = {h.name: h for h in hooks}
        self._file, self._host, self._port, self._max_bytes = state, host, port, max_bytes
        self._pending: list[dict[str, Any]] = []
        self._arrived = asyncio.Event()
        self._server: EmbeddedServer | None = None
        self.app = self._app()

    async def start(self) -> None:
        pending = self._file.load().get("pending")
        self._pending = [p for p in pending if isinstance(p, dict)] if isinstance(pending, list) else []
        self._arrived.set()
        server = EmbeddedServer(self.app, host=self._host, port=self._port)
        await server.listen(self.name)
        self._server = server

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            await server.stop()

    async def items(self) -> AsyncGenerator[Incoming]:
        while True:
            while self._pending:
                yield incoming(self.name, self._pending[0])
                self._pending.pop(0)  # taken: the next one is asked for
                await self._file.save({"pending": self._pending})
            self._arrived.clear()
            await self._arrived.wait()

    def _app(self) -> FastAPI:
        app = FastAPI(title="Nestor, webhooks", docs_url=None, redoc_url=None, openapi_url=None)

        @app.post("/hooks/{name}")
        async def posted(name: str, request: Request) -> Response:
            hook = self._hooks.get(name)
            if hook is None:
                return Response(status_code=404)
            body = await read_body(request, self._max_bytes)
            if body is None:
                return Response(status_code=413)
            if not proven(hook.secret.get_secret_value(), request, body):
                log.warning("%s: a post to %s without its secret was refused", self.name, name)
                return Response(status_code=401)
            try:
                payload = json.loads(body)
            except ValueError:
                return JSONResponse({"error": "the body is not JSON"}, status_code=400)
            if len(self._pending) >= PENDING:
                return Response(status_code=503, headers={"Retry-After": "60"})
            post = {
                "id": new_id(),
                "hook": hook.name,
                "kind": hook.kind,
                "event": next((request.headers[h] for h in EVENTS if h in request.headers), None),
                "payload": payload,
            }
            self._pending.append(post)
            await self._file.save({"pending": self._pending})
            self._arrived.set()
            return JSONResponse({"accepted": post["id"]}, status_code=202)

        return app

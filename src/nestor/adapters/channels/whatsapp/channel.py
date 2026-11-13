"""The WhatsApp channel: the webhook it serves, and the answers it sends through the Cloud API."""

import asyncio
import hmac
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response

from nestor.adapters.channels.messaging import Incoming, MessagingChannel, split_text
from nestor.adapters.channels.whatsapp.api import GRAPH, CloudApi
from nestor.adapters.channels.whatsapp.webhook import messages
from nestor.adapters.common.http import signature
from nestor.core import ProviderError
from nestor.modules.channels import Answer, AttachmentKind
from nestor.runtime.server import EmbeddedServer

logger = logging.getLogger(__name__)

MESSAGE_LIMIT = 4096
FILE_LIMIT = 100 * 1024 * 1024  # what the Cloud API serves
SEEN = 1000  # message ids kept to answer each message once


class WhatsAppChannel(MessagingChannel):
    name = "whatsapp"
    brand = "whatsapp"
    file_limit = FILE_LIMIT
    sends = frozenset({AttachmentKind.IMAGE, AttachmentKind.VOICE})

    def __init__(
        self,
        channel_id: str,
        *,
        phone_number_id: str,
        token: str,
        verify_token: str,
        app_secret: str,
        host: str = "127.0.0.1",
        port: int = 8473,
        api: str = GRAPH,
        transport: httpx.AsyncBaseTransport | None = None,
        **common: Any,
    ) -> None:
        """`common`: what every `MessagingChannel` takes (`apology`, `retry_delay_s`…)."""
        super().__init__(channel_id, **common)
        self._verify_token, self._app_secret = verify_token, app_secret
        self._api = CloudApi(phone_number_id, token, api=api, transport=transport)
        self._host, self._port = host, port
        self._received: asyncio.Queue[Incoming] = asyncio.Queue()
        self._seen: dict[str, None] = {}  # the ids of the last messages received, oldest first
        self._server: EmbeddedServer | None = None

    def app(self) -> FastAPI:
        """The webhook Meta calls: its verification (GET) and the messages (POST)."""
        app = FastAPI(title="Nestor, WhatsApp webhook", docs_url=None, redoc_url=None, openapi_url=None)

        @app.get("/whatsapp")
        async def verify(request: Request) -> Response:
            query = request.query_params
            if query.get("hub.mode") == "subscribe" and hmac.compare_digest(
                query.get("hub.verify_token", ""), self._verify_token
            ):
                return PlainTextResponse(query.get("hub.challenge", ""))
            return Response(status_code=403)

        @app.post("/whatsapp")
        async def notified(request: Request) -> Response:
            body = await request.body()
            expected = signature(self._app_secret, body)
            if not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected):
                logger.warning("whatsapp: a post without Meta's signature was refused")
                return Response(status_code=401)
            for message_id, incoming in messages(json.loads(body), self.channel_id, self._api):
                if message_id not in self._seen:  # Meta delivers at least once, sometimes twice
                    self._seen[message_id] = None
                    if len(self._seen) > SEEN:
                        del self._seen[next(iter(self._seen))]
                    self._received.put_nowait(incoming)
            return Response(status_code=200)

        return app

    async def receive(self) -> AsyncIterator[Incoming]:
        self._server = EmbeddedServer(self.app(), host=self._host, port=self._port)
        serving = asyncio.create_task(self._server.serve())
        try:
            while not self.closed:
                received = asyncio.ensure_future(self._received.get())
                await asyncio.wait({received, serving}, return_when=asyncio.FIRST_COMPLETED)
                if serving.done():  # the port could not be served, or the channel closed
                    received.cancel()
                    if not self.closed:
                        serving.result()  # its error, when it failed
                        raise ProviderError(self.name, f"the webhook stopped serving port {self._port}", transient=True)
                    return
                yield received.result()
        finally:
            self._server.should_exit = True
            await asyncio.wait({serving})

    async def disconnect(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        await self._api.aclose()

    async def deliver(self, conversation: str, answer: Answer) -> None:
        """The recording when it has one (WhatsApp shows no caption on a voice message: the text follows it), the
        text otherwise; then the pictures.
        """
        if answer.voice is not None:
            await self._api.send(conversation, "audio", {"id": await self._api.upload(answer.voice)})
        else:
            for part in split_text(answer.text, MESSAGE_LIMIT):
                await self._api.send(conversation, "text", {"body": part})
        for picture in (a for a in answer.attachments if a.kind is AttachmentKind.IMAGE):
            await self._api.send(conversation, "image", {"id": await self._api.upload(picture)})

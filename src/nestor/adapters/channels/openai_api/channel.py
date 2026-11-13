"""The OpenAI-compatible API channel: its server, the keys of the household's accounts, a turn for each request."""

import asyncio
import hmac
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from nestor.adapters.channels.openai_api.wire import completion, error, last_user_message, model, stream, thread, whole
from nestor.core import ProviderError
from nestor.modules.channels import Address, Assistant, Attachment, Channel, InboundMessage, Medium, Sender
from nestor.runtime.server import EmbeddedServer


class OpenAIApiChannel(Channel):
    name = "openai-api"
    brand = "openai"

    def __init__(
        self,
        channel_id: str,
        *,
        keys: Mapping[str, str],
        host: str = "127.0.0.1",
        port: int = 8472,
        conversation_ends_after_s: float | None = None,
    ) -> None:
        """`keys`: by account name, the key that account's client sends (`Authorization: Bearer <key>`)."""
        super().__init__(channel_id, conversation_ends_after_s=conversation_ends_after_s)
        self._keys = dict(keys)
        self._host, self._port = host, port
        self._server: EmbeddedServer | None = None
        self._closed = asyncio.Event()

    def app(self, assistant: Assistant) -> FastAPI:
        """The API, answering through `assistant`."""
        app = FastAPI(title="Nestor, OpenAI-compatible", docs_url=None, redoc_url=None, openapi_url=None)

        @app.get("/v1/models")
        async def models(request: Request) -> Response:
            if self._account(request) is None:
                return error(401, "invalid_api_key", "Incorrect API key provided.")
            return JSONResponse({"object": "list", "data": [model()]})

        @app.post("/v1/chat/completions")
        async def completions(request: Request) -> Response:
            account = self._account(request)
            if account is None:
                return error(401, "invalid_api_key", "Incorrect API key provided.")
            try:
                body = await request.json()
                text, attachments = last_user_message(body["messages"])
                client_thread = thread(body["messages"])
            except (ValueError, KeyError, TypeError, StopIteration):
                return error(400, "invalid_request_error", "`messages` needs a message from the user.")
            address, sender = Address(self.channel_id, f"{account}/{client_thread}"), Sender(account)
            if assistant.identify(address, sender) is None:
                return error(403, "permission_denied", f"{account} is not an account of the household.")
            message = InboundMessage(address=address, sender=sender, text=text, attachments=attachments)
            reply = assistant.respond(message)
            if body.get("stream"):
                return StreamingResponse(stream(reply), media_type="text/event-stream")
            return JSONResponse(completion(await whole(reply)))

        return app

    async def serve(self, assistant: Assistant) -> None:
        if self._closed.is_set():
            return
        self._server = EmbeddedServer(self.app(assistant), host=self._host, port=self._port)
        await self._server.serve()

    async def send(self, to: Address, text: str, medium: Medium, attachments: tuple[Attachment, ...]) -> None:
        raise ProviderError(self.name, "an API answers its clients, it cannot write to them", transient=False)

    def reachable(self, to: Address, medium: Medium) -> bool:
        return False

    async def close(self) -> None:
        self._closed.set()
        if self._server is not None:
            self._server.should_exit = True

    def _account(self, request: Request) -> str | None:
        """The account whose key the request bears; `None` for none of them."""
        scheme, _, key = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not key.strip():
            return None
        given = key.strip().encode()
        return next((name for name, known in self._keys.items() if hmac.compare_digest(given, known.encode())), None)

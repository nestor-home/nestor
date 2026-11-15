"""The Telegram Bot HTTP API: a thin client that turns every failure into a `TelegramError`, and keeps the bot's token
out of the logs."""

import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from nestor.adapters.common.http import HttpApi, retryable
from nestor.core import ProviderError
from nestor.modules.channels import Attachment

PROVIDER = "telegram"
EVERY_ERROR = range(400, 600)
FILE_BYTES = 20 * 1024 * 1024  # what the Bot API lets a bot download
_TOKEN_IN_URL = re.compile(r"/bot[^/\s]+/")


class _RedactBotToken(logging.Filter):
    """httpx logs every request URL at info level, and the Bot API puts the token in the path."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = _TOKEN_IN_URL.sub("/bot<redacted>/", record.getMessage()), None
        return True


logging.getLogger("httpx").addFilter(_RedactBotToken())


class TelegramError(ProviderError):
    """A call Telegram refused, with how long to wait when it asks to slow down (`retry_after_s`)."""

    def __init__(self, message: str, *, transient: bool, retry_after_s: float | None = None) -> None:
        super().__init__(PROVIDER, message, transient=transient, retry_after_s=retry_after_s)


class _ResponseParameters(BaseModel):
    retry_after: float | None = None


class _Envelope(BaseModel):
    ok: bool
    result: Any = None
    error_code: int | None = None
    description: str = ""
    parameters: _ResponseParameters | None = None


class BotApi:
    """A thin client of the Telegram Bot HTTP API: a call that Telegram refuses is a `TelegramError` (with how long to
    wait when it asks to slow down), one that does not reach it a `ProviderError`; the token, in every path, is never
    shown."""

    def __init__(
        self,
        token: str,
        *,
        api_base: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._api = HttpApi(PROVIDER, api_base, secret=token, timeout_s=timeout_s, transport=transport)

    async def call(self, method: str, payload: dict[str, object], *, timeout_s: float | None = None) -> Any:
        timeout = httpx.USE_CLIENT_DEFAULT if timeout_s is None else timeout_s
        return self._result(method, await self._post(method, json=payload, timeout=timeout))

    async def upload(self, method: str, fields: dict[str, str], name: str, file: Attachment) -> Any:
        """`method` with `file` sent as its `name` field, the other fields beside it."""
        upload = {name: (file.name or name, file.data, file.media_type)}
        return self._result(method, await self._post(method, data=fields, files=upload))

    async def download(self, file_id: str, *, max_bytes: int = FILE_BYTES) -> bytes:
        """A file of a message, by its id."""
        found = await self.call("getFile", {"file_id": file_id})
        path = found.get("file_path") if isinstance(found, dict) else None
        if not isinstance(path, str):
            raise TelegramError("getFile: no file path", transient=False)
        return await self._api.download(f"/file/bot{self._token}/{path}", max_bytes=max_bytes)

    async def _post(self, method: str, **request: Any) -> httpx.Response:
        # Telegram answers every refusal with its own envelope: read, whatever the status
        return await self._api.request("POST", f"/bot{self._token}/{method}", answers=EVERY_ERROR, **request)

    def _result(self, method: str, response: httpx.Response) -> Any:
        try:
            envelope = _Envelope.model_validate_json(response.content)
        except ValidationError:
            raise TelegramError(
                f"{method}: HTTP {response.status_code}", transient=retryable(response.status_code)
            ) from None
        if envelope.ok:
            return envelope.result
        code = envelope.error_code or response.status_code
        retry_after = envelope.parameters.retry_after if envelope.parameters else None
        raise TelegramError(
            f"{method}: {code} {envelope.description}".strip(), transient=retryable(code), retry_after_s=retry_after
        )

    async def aclose(self) -> None:
        await self._api.aclose()

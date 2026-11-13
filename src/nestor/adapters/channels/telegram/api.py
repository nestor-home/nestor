"""The Telegram Bot HTTP API: a thin client that turns every failure into a `TelegramError`, and keeps the bot's token
out of the logs."""

import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from nestor.core import ProviderError
from nestor.modules.channels import Attachment

PROVIDER = "telegram"
_TOKEN_IN_URL = re.compile(r"/bot[^/\s]+/")


class _RedactBotToken(logging.Filter):
    """httpx logs every request URL at info level, and the Bot API puts the token in the path."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = _TOKEN_IN_URL.sub("/bot<redacted>/", record.getMessage()), None
        return True


logging.getLogger("httpx").addFilter(_RedactBotToken())


class TelegramError(ProviderError):
    """A failed Bot API call; `retry_after_s` is set when Telegram asks to slow down."""

    def __init__(self, message: str, *, transient: bool, retry_after_s: float | None = None) -> None:
        super().__init__(PROVIDER, message, transient=transient)
        self.retry_after_s = retry_after_s


class _ResponseParameters(BaseModel):
    retry_after: float | None = None


class _Envelope(BaseModel):
    ok: bool
    result: Any = None
    error_code: int | None = None
    description: str = ""
    parameters: _ResponseParameters | None = None


class BotApi:
    """A thin client of the Telegram Bot HTTP API that turns every failure into a `TelegramError`."""

    def __init__(
        self,
        token: str,
        *,
        api_base: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._client = httpx.AsyncClient(base_url=api_base, timeout=timeout_s, transport=transport)

    async def call(self, method: str, payload: dict[str, object], *, timeout_s: float | None = None) -> Any:
        timeout = httpx.USE_CLIENT_DEFAULT if timeout_s is None else timeout_s
        return self._result(method, await self._post(method, json=payload, timeout=timeout))

    async def upload(self, method: str, fields: dict[str, str], name: str, file: Attachment) -> Any:
        """`method` with `file` sent as its `name` field, the other fields beside it."""
        upload = {name: (file.name or name, file.data, file.media_type)}
        return self._result(method, await self._post(method, data=fields, files=upload))

    async def download(self, file_id: str) -> bytes:
        """A file of a message, by its id."""
        found = await self.call("getFile", {"file_id": file_id})
        path = found.get("file_path") if isinstance(found, dict) else None
        if not isinstance(path, str):
            raise TelegramError("getFile: no file path", transient=False)
        response = await self._request("download", "GET", f"/file/bot{self._token}/{path}")
        if response.is_error:
            raise TelegramError(f"download: HTTP {response.status_code}", transient=_transient(response.status_code))
        return response.content

    async def _post(self, method: str, **request: Any) -> httpx.Response:
        return await self._request(method, "POST", f"/bot{self._token}/{method}", **request)

    async def _request(self, what: str, verb: str, path: str, **request: Any) -> httpx.Response:
        try:
            return await self._client.request(verb, path, **request)
        except httpx.HTTPError as error:
            detail = f"{type(error).__name__} {error}".replace(self._token, "<redacted>")
            raise TelegramError(f"{what}: {detail.strip()}", transient=True) from None

    def _result(self, method: str, response: httpx.Response) -> Any:
        try:
            envelope = _Envelope.model_validate_json(response.content)
        except ValidationError:
            raise TelegramError(
                f"{method}: HTTP {response.status_code}", transient=_transient(response.status_code)
            ) from None
        if envelope.ok:
            return envelope.result
        code = envelope.error_code or response.status_code
        retry_after = envelope.parameters.retry_after if envelope.parameters else None
        raise TelegramError(
            f"{method}: {code} {envelope.description}".strip(), transient=_transient(code), retry_after_s=retry_after
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _transient(status: int) -> bool:
    """Rate limits, server errors and a conflict (another instance polling with the same token, which
    ends with it) may pass; a bad token (401), a blocked bot (403) or a bad request won't."""
    return status in (409, 429) or status >= 500

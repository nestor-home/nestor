"""ElevenLabs' HTTP API, for recordings (a voice message to transcribe, an answer to record): every failure becomes a
`ProviderError` with the key redacted."""

import httpx

from nestor.adapters.models.common import detail, provider_error, retryable
from nestor.core import ProviderError

PROVIDER = "elevenlabs"
API = "https://api.elevenlabs.io"


class ElevenLabsApi:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = API,
        timeout_s: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url, self._timeout_s, self._transport = base_url, timeout_s, transport

    async def post(
        self,
        path: str,
        *,
        json: object = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {"xi-api-key": self._api_key}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post(path, headers=headers, json=json, data=data, files=files, params=params)
        except httpx.HTTPError as error:
            raise self._error(f"{path}: {type(error).__name__} {error}".strip(), transient=True) from None
        if response.is_error:
            raise self._error(
                f"{path}: HTTP {response.status_code} {detail(response.content)}",
                transient=retryable(response.status_code),
            )
        return response

    def _error(self, message: str, *, transient: bool) -> ProviderError:
        return provider_error(PROVIDER, self._api_key, message, transient=transient)

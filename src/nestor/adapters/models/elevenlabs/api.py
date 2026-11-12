"""ElevenLabs' HTTP API, for recordings (a voice message to transcribe, an answer to record): every failure becomes a
`ProviderError` with the key redacted."""

import httpx

from nestor.adapters.common.http import detail, provider_error, retryable
from nestor.core import ProviderError

PROVIDER = "elevenlabs"
API = "https://api.elevenlabs.io"
TIMEOUT_S = 60.0  # a long voice message takes a while to transcribe or record


class ElevenLabsApi:
    """One HTTP client, opened on the first call and kept until `aclose`: a recording does not pay a new connection."""

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api_key, self._transport = api_key, transport
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

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
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=API, timeout=TIMEOUT_S, transport=self._transport)
        try:
            response = await self._client.post(path, headers=headers, json=json, data=data, files=files, params=params)
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

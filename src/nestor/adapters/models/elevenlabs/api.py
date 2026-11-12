"""ElevenLabs' HTTP API, for recordings (a voice message to transcribe, an answer to record): every failure becomes a
`ProviderError` with the key redacted."""

import httpx

from nestor.adapters.common.http import HttpApi

PROVIDER = "elevenlabs"
API = "https://api.elevenlabs.io"
TIMEOUT_S = 60.0  # a long voice message takes a while to transcribe or record


def elevenlabs_api(api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> HttpApi:
    return HttpApi(
        PROVIDER, API, headers={"xi-api-key": api_key}, secret=api_key, timeout_s=TIMEOUT_S, transport=transport
    )

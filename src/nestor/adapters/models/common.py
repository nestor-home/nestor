"""What the OpenAI-compatible adapters share: the hosted providers they know (each requires a key), which HTTP
errors a retry may get past, the detail of an error as the provider words it, and a key never shown in one."""

import json
import urllib.parse

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from nestor.core import ProviderError
from nestor.runtime.plugins import AdapterSettings

BRANDS = {"openrouter.ai": "openrouter", "openai.com": "openai", "mistral.ai": "mistral", "anthropic.com": "anthropic"}
MAX_DETAIL = 300
_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429})


def brand_host(base_url: str) -> str | None:
    """The known provider `base_url` belongs to (`openrouter.ai`), if any: each requires an API key."""
    host = urllib.parse.urlsplit(base_url).hostname or ""
    return next((suffix for suffix in BRANDS if host == suffix or host.endswith(f".{suffix}")), None)


def brand(base_url: str) -> str | None:
    return BRANDS.get(brand_host(base_url) or "")


def retryable(status: int) -> bool:
    return status in _RETRYABLE_STATUSES or status >= 500


def detail(body: bytes) -> str:
    """An error body as the provider words it: its `error.message` when it sends one."""
    text = body.decode(errors="replace")
    try:
        error = json.loads(text)["error"]
    except (ValueError, KeyError, TypeError):
        return text[:MAX_DETAIL]
    return message_of(error)


def message_of(error: object) -> str:
    message = error.get("message", error) if isinstance(error, dict) else error
    return str(message)[:MAX_DETAIL]


def provider_error(provider: str, api_key: str | None, message: str, *, transient: bool) -> ProviderError:
    """A `ProviderError` labelled with `provider`, the key redacted wherever the message quotes it."""
    redacted = message.replace(api_key, "[redacted]") if api_key else message
    return ProviderError(provider, redacted, transient=transient)


class EndpointSettings(AdapterSettings):
    """An OpenAI-compatible endpoint; `api_key` should come from the environment.

    The key is optional, as local servers need none: empty is the same as absent. The hosted providers known
    to require one refuse to be configured without it."""

    base_url: str
    api_key: SecretStr | None = Field(default=None, validate_default=True)

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_is_absent(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("api_key")
    @classmethod
    def _required_by_known_providers(cls, value: SecretStr | None, info: ValidationInfo) -> SecretStr | None:
        if value is None and (host := brand_host(str(info.data.get("base_url", "")))):
            raise PydanticCustomError("api_key_required", "{host} requires an API key", {"host": host})
        return value

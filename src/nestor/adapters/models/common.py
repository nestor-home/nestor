"""What the OpenAI-compatible adapters share: the hosted providers they know, each of which requires a key."""

import urllib.parse
from typing import Any

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from nestor.runtime.plugins import AdapterSettings

BRANDS = {  # host suffix → brand; published in `base_url`'s schema (`x-nestor.brands`) so the admin shows the same
    "openrouter.ai": "openrouter",
    "openai.com": "openai",
    "mistral.ai": "mistral",
    "anthropic.com": "anthropic",
    "generativelanguage.googleapis.com": "gemini",
    "groq.com": "groq",
}
BRANDED: dict[str, Any] = {"brands": BRANDS}  # the field the brand is read from


def brand_host(base_url: str) -> str | None:
    """The known provider `base_url` belongs to (`openrouter.ai`), if any: each requires an API key."""
    host = urllib.parse.urlsplit(base_url).hostname or ""
    return next((suffix for suffix in BRANDS if host == suffix or host.endswith(f".{suffix}")), None)


def brand(base_url: str) -> str | None:
    return BRANDS.get(brand_host(base_url) or "")


class EndpointSettings(AdapterSettings):
    """An OpenAI-compatible endpoint; `api_key` should come from the environment.

    The key is optional, as local servers need none: empty is the same as absent. The hosted providers known
    to require one refuse to be configured without it."""

    base_url: str = Field(json_schema_extra=BRANDED)
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

"""The settings of a Claude model, and how it is built from them."""

from typing import Any

from pydantic import Field, PositiveFloat, PositiveInt

from nestor.adapters.models.anthropic.language import MAX_TOKENS, AnthropicLanguage
from nestor.adapters.models.anthropic.wire import Effort
from nestor.runtime.plugins import AdapterSettings, RequiredSecret, Services


class AnthropicLanguageSettings(AdapterSettings):
    """Configuration of a Claude model over Anthropic's API."""

    api_key: RequiredSecret
    model: str = Field(min_length=1)  # e.g. claude-haiku-5-5, claude-sonnet-5-5
    # the longest answer, thinking included; lower it for an older model whose output limit is smaller
    max_tokens: PositiveInt = MAX_TOKENS
    effort: Effort | None = None  # the model's own default otherwise
    extra_body: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"advanced": True})
    base_url: str = Field(default="https://api.anthropic.com/v1", json_schema_extra={"advanced": True})
    connect_timeout_s: PositiveFloat = Field(default=5.0, json_schema_extra={"advanced": True})
    read_timeout_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})


def build_language(settings: AnthropicLanguageSettings, name: str, services: Services) -> AnthropicLanguage:
    return AnthropicLanguage(
        api_key=settings.api_key.get_secret_value(),
        model=settings.model,
        max_tokens=settings.max_tokens,
        effort=settings.effort,
        extra_body=settings.extra_body,
        base_url=settings.base_url,
        connect_timeout_s=settings.connect_timeout_s,
        read_timeout_s=settings.read_timeout_s,
        name=name,
    )

"""The settings of a Gemini model, and how it is built from them."""

from typing import Any

from pydantic import Field, PositiveFloat

from nestor.adapters.models.gemini.language import GeminiLanguage
from nestor.runtime.plugins import AdapterSettings, RequiredSecret, Services


class GeminiLanguageSettings(AdapterSettings):
    """Configuration of a Gemini model over Google's Gemini API (Google AI Studio's keys)."""

    api_key: RequiredSecret
    model: str = Field(min_length=1)  # e.g. gemini-2.5-flash
    # merged into every request: `generationConfig` (its `thinkingConfig`, `maxOutputTokens`…), `safetySettings`
    extra_body: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"advanced": True})
    base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta", json_schema_extra={"advanced": True}
    )
    connect_timeout_s: PositiveFloat = Field(default=5.0, json_schema_extra={"advanced": True})
    read_timeout_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})


def build_language(settings: GeminiLanguageSettings, name: str, services: Services) -> GeminiLanguage:
    return GeminiLanguage(
        api_key=settings.api_key.get_secret_value(),
        model=settings.model,
        extra_body=settings.extra_body,
        base_url=settings.base_url,
        connect_timeout_s=settings.connect_timeout_s,
        read_timeout_s=settings.read_timeout_s,
        name=name,
    )

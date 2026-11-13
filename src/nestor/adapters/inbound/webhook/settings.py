"""The webhooks as the configuration declares them."""

from pydantic import Field, PositiveInt, model_validator

from nestor.adapters.common.state import StateFile
from nestor.adapters.inbound.webhook.hooks import Hook
from nestor.adapters.inbound.webhook.source import WebhookSource
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class WebhookSettings(AdapterSettings):
    hooks: list[Hook] = Field(min_length=1)
    host: str = "127.0.0.1"
    port: int = Field(default=8474, ge=1, le=65535)
    max_bytes: PositiveInt = Field(default=65_536, json_schema_extra={"advanced": True})

    @model_validator(mode="after")
    def _distinct(self) -> "WebhookSettings":
        if len({h.name for h in self.hooks}) != len(self.hooks):
            raise ValueError("two hooks have the same name")
        return self


def build(settings: WebhookSettings, name: str, services: Services) -> WebhookSource:
    return WebhookSource(
        name,
        settings.hooks,
        StateFile(services.data_dir / "inbound" / f"{name}.json"),
        host=settings.host,
        port=settings.port,
        max_bytes=settings.max_bytes,
    )

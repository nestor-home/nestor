"""The webhook channel's settings and how it is built from them."""

from pydantic import SecretStr

from nestor.adapters.channels.webhook.channel import WebhookChannel
from nestor.core import Component
from nestor.runtime.plugins import ChannelSettings, Services


class WebhookSettings(ChannelSettings):
    url: str  # where each message is posted
    secret: SecretStr | None = None  # signs each body (X-Nestor-Signature)


def build(settings: WebhookSettings, name: str, services: Services) -> Component:
    return WebhookChannel(
        name, url=settings.url, secret=settings.secret.get_secret_value() if settings.secret else None
    )

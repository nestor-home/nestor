"""Configuration of the Telegram channel, and how it is built."""

from pydantic import Field

from nestor.adapters.channels.messaging import MessagingSettings
from nestor.adapters.channels.telegram.channel import TelegramChannel
from nestor.core import Component
from nestor.runtime.plugins import RequiredSecret, Services


class TelegramSettings(MessagingSettings):
    token: RequiredSecret
    api_base: str = "https://api.telegram.org"
    poll_timeout_s: int = Field(default=30, ge=1, le=50)
    request_timeout_s: float = Field(default=10.0, gt=0)


def build(settings: TelegramSettings, name: str, services: Services) -> Component:
    return TelegramChannel(
        name,
        token=settings.token.get_secret_value(),
        api_base=settings.api_base,
        poll_timeout_s=settings.poll_timeout_s,
        request_timeout_s=settings.request_timeout_s,
        **settings.common(services),
    )

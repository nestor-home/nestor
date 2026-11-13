"""Configuration of the Matrix channel, and how it is built."""

from pydantic import Field

from nestor.adapters.channels.matrix.channel import MatrixChannel
from nestor.adapters.channels.messaging import MessagingSettings
from nestor.core import Component
from nestor.runtime.plugins import RequiredSecret, Services


class MatrixSettings(MessagingSettings):
    homeserver: str  # https://matrix.example.org
    token: RequiredSecret  # the bot account's access token
    poll_timeout_s: int = Field(default=30, ge=1, le=120)


def build(settings: MatrixSettings, name: str, services: Services) -> Component:
    return MatrixChannel(
        name,
        homeserver=settings.homeserver,
        token=settings.token.get_secret_value(),
        poll_timeout_s=settings.poll_timeout_s,
        **settings.common(services),
    )

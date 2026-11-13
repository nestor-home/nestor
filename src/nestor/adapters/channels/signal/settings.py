"""Configuration of the Signal channel, and how it is built."""

from pydantic import Field

from nestor.adapters.channels.messaging import MessagingSettings
from nestor.adapters.channels.signal.channel import SignalChannel
from nestor.core import Component
from nestor.runtime.plugins import Services


class SignalSettings(MessagingSettings):
    url: str  # signal-cli-rest-api, e.g. http://signal:8080
    number: str = Field(min_length=2)  # the bot's number as registered with signal-cli, +33…
    wait_s: int = Field(default=30, ge=1, le=120, json_schema_extra={"advanced": True})


def build(settings: SignalSettings, name: str, services: Services) -> Component:
    return SignalChannel(
        name, url=settings.url, number=settings.number, wait_s=settings.wait_s, **settings.common(services)
    )

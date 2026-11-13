"""Configuration of the admin's chat channel, and how it is built."""

from nestor.core import Component
from nestor.modules.channels import ChatChannel
from nestor.runtime.plugins import ChannelSettings, Services


class WebSettings(ChannelSettings):
    pass


def build(settings: WebSettings, name: str, services: Services) -> Component:
    return ChatChannel(name, conversation_ends_after_s=settings.conversation_ends_after_s)

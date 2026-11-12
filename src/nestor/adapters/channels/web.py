"""The admin's chat as a channel: `kind: web`. The chat itself is the domain's (`ChatChannel`); the admin serves it."""

from nestor.core import Component
from nestor.modules.channels import ChatChannel
from nestor.runtime.plugins import ChannelSettings, Family, Plugin, Services


class WebSettings(ChannelSettings):
    pass


def build(settings: WebSettings, name: str, services: Services) -> Component:
    return ChatChannel(name, conversation_ends_after_s=settings.conversation_ends_after_s)


plugin = Plugin(Family.CHANNEL, "web", WebSettings, build)

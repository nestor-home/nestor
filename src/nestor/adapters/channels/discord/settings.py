"""Configuration of the Discord channel, and how it is built."""

from nestor.adapters.channels.discord.channel import DiscordChannel
from nestor.adapters.channels.messaging import MessagingSettings
from nestor.core import Component
from nestor.runtime.plugins import RequiredSecret, Services


class DiscordSettings(MessagingSettings):
    token: RequiredSecret  # the bot's token (Developer Portal, Bot)


def build(settings: DiscordSettings, name: str, services: Services) -> Component:
    return DiscordChannel(name, token=settings.token.get_secret_value(), **settings.common(services))

"""Configuration of the Slack channel, and how it is built."""

from nestor.adapters.channels.messaging import MessagingSettings
from nestor.adapters.channels.slack.channel import SlackChannel
from nestor.core import Component
from nestor.runtime.plugins import RequiredSecret, Services


class SlackSettings(MessagingSettings):
    app_token: RequiredSecret  # xapp-…, with connections:write (Socket Mode)
    bot_token: RequiredSecret  # xoxb-…


def build(settings: SlackSettings, name: str, services: Services) -> Component:
    return SlackChannel(
        name,
        app_token=settings.app_token.get_secret_value(),
        bot_token=settings.bot_token.get_secret_value(),
        **settings.common(services),
    )

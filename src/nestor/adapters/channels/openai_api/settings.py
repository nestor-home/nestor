"""The OpenAI-compatible API channel's settings and how it is built from them."""

from pydantic import Field

from nestor.adapters.channels.openai_api.channel import OpenAIApiChannel
from nestor.core import Component
from nestor.runtime.plugins import ChannelSettings, RequiredSecret, Services


class OpenAIApiSettings(ChannelSettings):
    keys: dict[str, RequiredSecret] = Field(min_length=1)  # by account name: openai-api:<name> in `household`
    host: str = "127.0.0.1"  # 0.0.0.0 for clients on other machines
    port: int = Field(default=8472, ge=1, le=65535)


def build(settings: OpenAIApiSettings, name: str, services: Services) -> Component:
    return OpenAIApiChannel(
        name,
        keys={account: key.get_secret_value() for account, key in settings.keys.items()},
        host=settings.host,
        port=settings.port,
        conversation_ends_after_s=settings.conversation_ends_after_s,
    )

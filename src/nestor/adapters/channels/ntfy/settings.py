"""The ntfy channel's settings and how it is built from them."""

from pydantic import SecretStr

from nestor.adapters.channels.ntfy.channel import NtfyChannel
from nestor.core import Component
from nestor.runtime.plugins import ChannelSettings, Services


class NtfySettings(ChannelSettings):
    url: str = "https://ntfy.sh"
    token: SecretStr | None = None  # an access token, for a server with access control


def build(settings: NtfySettings, name: str, services: Services) -> Component:
    token = settings.token.get_secret_value() if settings.token else None
    return NtfyChannel(name, url=settings.url, token=token)

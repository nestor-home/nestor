"""The WhatsApp channel's settings, and how it is built from them."""

from pydantic import Field

from nestor.adapters.channels.messaging import MessagingSettings
from nestor.adapters.channels.whatsapp.channel import WhatsAppChannel
from nestor.core import Component
from nestor.runtime.plugins import RequiredSecret, Services


class WhatsAppSettings(MessagingSettings):
    phone_number_id: str = Field(min_length=1)  # the number's id, in Meta's app dashboard (not the number itself)
    token: RequiredSecret  # a permanent access token of a system user
    verify_token: RequiredSecret  # what Meta sends when the webhook is set up, chosen by the household
    app_secret: RequiredSecret  # the app's secret, which signs every post
    host: str = "127.0.0.1"  # the reverse proxy forwards https://<host>/whatsapp here
    port: int = Field(default=8473, ge=1, le=65535)


def build(settings: WhatsAppSettings, name: str, services: Services) -> Component:
    return WhatsAppChannel(
        name,
        phone_number_id=settings.phone_number_id,
        token=settings.token.get_secret_value(),
        verify_token=settings.verify_token.get_secret_value(),
        app_secret=settings.app_secret.get_secret_value(),
        host=settings.host,
        port=settings.port,
        **settings.common(services),
    )

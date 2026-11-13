"""The feeds as the configuration declares them."""

from pydantic import Field

from nestor.adapters.common.web import FEEDS
from nestor.adapters.inbound.polled import (
    Address,
    PolledSettings,
    state_folder,
    to_watch,
)
from nestor.adapters.inbound.rss.source import FeedSource
from nestor.core import Component
from nestor.runtime import Services


class RssSettings(PolledSettings):
    feeds: list[Address] = Field(min_length=1)
    every_s: float = Field(default=900.0, ge=60.0)  # between two checks of each feed


def build(settings: RssSettings, name: str, services: Services) -> Component:
    return FeedSource(
        name,
        to_watch(settings.feeds),
        settings.web(FEEDS),
        state_folder(services, name),
        every_s=settings.every_s,
        deadline_s=settings.timeout_s,
    )

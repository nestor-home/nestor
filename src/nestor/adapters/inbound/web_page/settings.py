"""The pages as the configuration declares them."""

from pydantic import Field

from nestor.adapters.common.web import PAGES
from nestor.adapters.documents import FileReader
from nestor.adapters.inbound.polled import (
    Address,
    PolledSettings,
    state_folder,
    to_watch,
)
from nestor.adapters.inbound.web_page.source import PageSource
from nestor.core import Component
from nestor.runtime import Services


class WebPageSettings(PolledSettings):
    pages: list[Address] = Field(min_length=1)
    every_s: float = Field(default=3600.0, ge=300.0)  # between two reads of each page


def build(settings: WebPageSettings, name: str, services: Services) -> Component:
    return PageSource(
        name,
        to_watch(settings.pages),
        settings.web(PAGES),
        state_folder(services, name),
        every_s=settings.every_s,
        deadline_s=settings.timeout_s,
        reader=FileReader(),
    )

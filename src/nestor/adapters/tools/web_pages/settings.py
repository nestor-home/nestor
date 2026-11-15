"""Configuration of the page reader, and how it is built."""

from pydantic import Field, PositiveFloat, PositiveInt

from nestor.adapters.documents import FileReader
from nestor.adapters.tools.web_pages.tools import WebPages
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class WebPagesSettings(AdapterSettings):
    timeout_s: PositiveFloat = 15.0
    max_bytes: PositiveInt = Field(default=5_000_000, json_schema_extra={"advanced": True})


def build(settings: WebPagesSettings, name: str, services: Services) -> WebPages:
    pages = WebPages(FileReader(), timeout_s=settings.timeout_s, max_bytes=settings.max_bytes)
    pages.name = name
    return pages

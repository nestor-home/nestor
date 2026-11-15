"""The free web search's settings: which free tiers, in which order of the turn."""

from enum import StrEnum

from pydantic import Field

from nestor.adapters.tools.free_web_search.engine import Engine
from nestor.adapters.tools.free_web_search.exa import Exa
from nestor.adapters.tools.free_web_search.firecrawl import Firecrawl
from nestor.adapters.tools.free_web_search.keenable import Keenable
from nestor.adapters.tools.free_web_search.parallel import Parallel
from nestor.adapters.tools.free_web_search.search import FreeWebSearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class Tier(StrEnum):
    EXA = "exa"
    PARALLEL = "parallel"
    FIRECRAWL = "firecrawl"
    KEENABLE = "keenable"


ENGINES: dict[Tier, type[Engine]] = {
    Tier.EXA: Exa,
    Tier.PARALLEL: Parallel,
    Tier.FIRECRAWL: Firecrawl,
    Tier.KEENABLE: Keenable,
}


class FreeWebSearchSettings(AdapterSettings):
    engines: list[Tier] = Field(default_factory=lambda: list(Tier), min_length=1)  # taken in turn, in this order


def build(settings: FreeWebSearchSettings, name: str, services: Services) -> FreeWebSearch:
    search = FreeWebSearch([ENGINES[tier]() for tier in dict.fromkeys(settings.engines)])
    search.name = name
    return search

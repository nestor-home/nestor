"""The free tiers taken in turn: each search starts with the next one, goes on when a tier is busy, down or turns it
away, stops on a query refused as such, and tells the agent it runs on free tiers."""

from collections.abc import Sequence

import pytest

from nestor.adapters.common.http import StatusError
from nestor.adapters.tools.free_web_search.engine import Engine
from nestor.adapters.tools.free_web_search.search import FreeWebSearch
from nestor.core import ProviderError
from nestor.modules.web import Found

PAGE = Found(title="Majordome", url="https://example.org/majordome")
BUSY = StatusError("tier", 429, "", "slow down")
DOWN = ProviderError("tier", "ConnectError", transient=True)
TURNED_AWAY = StatusError("tier", 403, "", "your IP address looks suspicious")
BAD_QUERY = StatusError("tier", 400, "", "query too long")


class Tier(Engine):
    def __init__(self, name: str, asked: list[str], fails: ProviderError | None = None) -> None:
        self.name, self.label, self._asked, self._fails = name, name.title(), asked, fails

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        self._asked.append(self.name)
        if self._fails:
            raise self._fails
        return [PAGE]

    async def aclose(self) -> None: ...


async def test_each_search_starts_with_the_next_tier() -> None:
    asked: list[str] = []
    search = FreeWebSearch([Tier(n, asked) for n in ("exa", "parallel", "firecrawl")])
    for _ in range(4):
        await search.search("majordome", limit=1)
    start = ["exa", "parallel", "firecrawl"].index(asked[0])
    assert asked == [["exa", "parallel", "firecrawl"][(start + i) % 3] for i in range(4)]


@pytest.mark.parametrize("failure", [BUSY, DOWN, TURNED_AWAY], ids=["busy", "down", "turned away"])
async def test_a_tier_that_cannot_answer_now_hands_over_to_the_others(failure: ProviderError) -> None:
    asked: list[str] = []
    search = FreeWebSearch([Tier("exa", asked, failure), Tier("keenable", asked)])
    assert [list(await search.search("majordome", limit=1)) for _ in range(2)] == [[PAGE], [PAGE]]
    assert asked.count("exa") == 1, "tried once, at its turn"


async def test_a_query_refused_as_such_is_not_sent_to_the_others() -> None:
    asked: list[str] = []
    search = FreeWebSearch([Tier("exa", asked, BAD_QUERY), Tier("keenable", asked, BAD_QUERY)])
    with pytest.raises(StatusError, match="query too long"):
        await search.search("majordome " * 500, limit=1)
    assert len(asked) == 1


async def test_when_every_tier_is_busy_the_search_fails_naming_each_and_may_be_retried() -> None:
    asked: list[str] = []
    search = FreeWebSearch([Tier("exa", asked, BUSY), Tier("keenable", asked, TURNED_AWAY)])
    with pytest.raises(ProviderError) as failed:
        await search.search("majordome", limit=1)
    assert failed.value.transient
    assert "exa: " in str(failed.value) and "keenable: " in str(failed.value)


def test_the_agent_is_told_its_search_runs_on_free_tiers_and_what_a_key_would_change() -> None:
    [note] = FreeWebSearch([Tier("exa", []), Tier("keenable", [])]).notes()
    assert "free tiers of Exa and Keenable" in note and "API key" in note

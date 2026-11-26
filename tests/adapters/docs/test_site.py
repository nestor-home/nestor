"""The documentation read online: a page in Markdown from nestorhome.dev, read once, and an error the agent can answer
around when the site cannot be reached. Names resolve through a fake DNS; pages through mocked HTTP."""

from collections.abc import Iterator

import httpx
import pytest
import respx

from nestor.adapters.docs import SiteDocumentation
from nestor.core import ProviderError
from nestor.modules.system.selfmap.assistant import anchor, excerpt
from nestor.runtime.plugins import BUILT_IN, Registry
from nestor.runtime.selfmap import survey

from ..dns import resolve

TOOLS = "# Tools\n\n## Search\n\nAll engines serve one `web_search`.\n"


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> None:
    resolve(monkeypatch, {"nestorhome.dev": "185.199.108.153"})


@pytest.fixture
def site() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


async def test_a_page_is_its_markdown_read_once(site: respx.MockRouter) -> None:
    route = site.get("https://nestorhome.dev/docs/tools.md").respond(200, text=TOOLS)
    async with SiteDocumentation() as docs:
        assert await docs.page("tools") == TOOLS
        assert await docs.page("tools") == TOOLS
    assert route.call_count == 1


@pytest.mark.parametrize(
    "answer", [httpx.Response(404, text="Not found"), httpx.ConnectError("offline")], ids=["no page", "offline"]
)
async def test_a_page_that_cannot_be_read_is_a_provider_error(
    site: respx.MockRouter, answer: httpx.Response | Exception
) -> None:
    site.get("https://nestorhome.dev/docs/nope.md").mock(
        side_effect=answer if isinstance(answer, Exception) else None,
        return_value=answer if isinstance(answer, httpx.Response) else None,
    )
    async with SiteDocumentation() as docs:
        with pytest.raises(ProviderError):
            await docs.page("nope")


@pytest.mark.live
async def test_live_every_built_in_card_names_a_page_and_a_section_the_site_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()  # the real DNS
    with respx.mock(assert_all_called=False) as router:
        router.route(host="nestorhome.dev").pass_through()
        parts = survey(Registry.installed(distribution=BUILT_IN), []).parts
        async with SiteDocumentation() as docs:
            for card in {p.card for p in parts}:
                page = await docs.page(card.page)
                heading = excerpt(page, card.section).splitlines()[0].lstrip("#")
                assert card.section is None or anchor(heading) == card.section, card.docs

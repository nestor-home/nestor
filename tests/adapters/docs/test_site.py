"""The documentation read online: a page in Markdown from nestorhome.dev, read once, and an error the agent can answer
around when the site cannot be reached or is too slow. Names resolve through a fake DNS; pages through mocked HTTP."""

import asyncio
from collections.abc import Iterator

import httpx
import pytest
import respx

from nestor.adapters.docs import SiteDocumentation
from nestor.core import ProviderError
from nestor.modules.system.selfmap.assistant import anchor, excerpt
from nestor.runtime.plugins import BUILT_IN, Registry
from nestor.runtime.selfmap import survey
from nestor.testing.system import PAGE, DocumentationContract, StaticDocumentation

from ..dns import resolve


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> None:
    resolve(monkeypatch, {"nestorhome.dev": "185.199.108.153"})


@pytest.fixture
def site() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


class TestSiteDocumentation(DocumentationContract):
    @pytest.fixture(autouse=True)
    def pages(self, site: respx.MockRouter) -> None:
        site.get("https://nestorhome.dev/docs/tools.md").respond(200, text=PAGE)
        site.get(host="nestorhome.dev").respond(404, text="Not found")

    def documentation(self) -> SiteDocumentation:
        return SiteDocumentation()

    def unreachable(self) -> SiteDocumentation:
        return SiteDocumentation("https://unknown.example/docs")  # a name the DNS does not know


class TestStaticDocumentation(DocumentationContract):
    def documentation(self) -> StaticDocumentation:
        return StaticDocumentation({"tools": PAGE})

    def unreachable(self) -> StaticDocumentation:
        return StaticDocumentation({"tools": PAGE}, offline=True)


async def test_a_page_is_read_once(site: respx.MockRouter) -> None:
    route = site.get("https://nestorhome.dev/docs/tools.md").respond(200, text=PAGE)
    async with SiteDocumentation() as docs:
        assert await docs.page("tools") == PAGE
        assert await docs.page("tools") == PAGE
    assert route.call_count == 1


async def test_a_site_too_slow_is_a_provider_error_within_the_timeout(site: respx.MockRouter) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, text=PAGE)

    site.get("https://nestorhome.dev/docs/tools.md").mock(side_effect=slow)
    async with SiteDocumentation(timeout_s=0.1) as docs:
        with pytest.raises(ProviderError, match="took longer"):
            await docs.page("tools")


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

"""Web pages watched for changes: a change of the page's content is an item showing what changed, an unchanged page
or a change of its menus is none, a change made while Nestor was down comes after it starts and once only, and a
page that cannot be reached, or off the public internet, yields nothing. Pages are served through mocked HTTP; names
resolve through a fake DNS."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx

from nestor.adapters.common.web import PAGES, PublicWeb
from nestor.adapters.documents import FileReader
from nestor.adapters.inbound.polled import Watched
from nestor.adapters.inbound.web_page import PageSource
from nestor.modules.initiative import Incoming

from ...dns import resolve

URL = "https://shop.example/lamp"
DNS = {"shop.example": "93.184.215.14", "nas.home": "192.168.1.20"}


def lamp(price: str, menu: str = "Accueil") -> str:
    return (
        f"<html><head><title>Lampe FADO</title></head><body><nav>{menu}</nav>"
        f"<main><h1>Lampe FADO</h1><p>Prix : {price}</p><p>En stock</p></main></body></html>"
    )


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> None:
    resolve(monkeypatch, DNS)


@pytest.fixture
def web() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def page_source(folder: Path, url: str = URL) -> PageSource:
    return PageSource(
        "pages",
        [Watched("la lampe", url)],
        PublicWeb(accept=PAGES),
        folder,
        every_s=0.01,
        reader=FileReader(),
    )


async def taken(source: PageSource, wait_s: float = 0.1) -> list[Incoming]:
    found: list[Incoming] = []

    async def take() -> None:
        async for item in source.items():
            found.append(item)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(take(), wait_s)
    return found


async def test_a_change_of_the_content_is_one_item_showing_what_changed(web: respx.MockRouter, tmp_path: Path) -> None:
    route = web.get(URL).respond(200, html=lamp("59 €"))
    async with page_source(tmp_path / "pages") as source:
        assert await taken(source) == [], "the page as it was first read is not a change"
        route.respond(200, html=lamp("45 €", menu="Soldes !"))
        (item,) = await taken(source)
    assert (item.kind, item.title, item.sender) == ("page", "Lampe FADO", "la lampe")
    assert "- Prix : 59 €\n+ Prix : 45 €" in item.body
    assert "Soldes" not in item.body, "menus are not the page's content"


async def test_a_change_of_menus_only_is_no_item(web: respx.MockRouter, tmp_path: Path) -> None:
    route = web.get(URL).respond(200, html=lamp("59 €"))
    async with page_source(tmp_path / "pages") as source:
        route.respond(200, html=lamp("59 €", menu="Soldes !"))
        assert await taken(source) == []


async def test_a_change_made_while_down_comes_after_a_restart_and_once(web: respx.MockRouter, tmp_path: Path) -> None:
    route = web.get(URL).respond(200, html=lamp("59 €"))
    async with page_source(tmp_path / "pages"):
        pass
    route.respond(200, html=lamp("45 €"))
    async with page_source(tmp_path / "pages") as restarted:
        assert len(await taken(restarted)) == 1
    async with page_source(tmp_path / "pages") as again:
        assert await taken(again) == []


async def test_an_unreachable_page_yields_nothing_until_it_answers_again(web: respx.MockRouter, tmp_path: Path) -> None:
    route = web.get(URL).respond(200, html=lamp("59 €"))
    async with page_source(tmp_path / "pages") as source:
        route.respond(503)
        assert await taken(source) == []
        route.respond(200, html=lamp("59 €"))
        assert await taken(source) == [], "an outage is not a change"
        route.respond(200, html=lamp("45 €"))
        assert len(await taken(source)) == 1


@pytest.mark.parametrize("url", ["http://nas.home:5000/", "http://192.168.1.1/admin", "http://[::1]/"])
async def test_a_page_off_the_public_internet_is_never_fetched(web: respx.MockRouter, tmp_path: Path, url: str) -> None:
    inside = web.route().respond(200, html=lamp("59 €"))
    async with page_source(tmp_path / "pages", url) as source:
        assert await taken(source) == []
    assert not inside.called


def long_page(first: str, last: str) -> str:
    """A page whose text runs past what is kept of it, `first` at its top and `last` at its bottom."""
    lines = "".join(f"<p>Article {n}, avec un peu de texte pour remplir.</p>" for n in range(3000))
    return f"<html><body><main><p>{first}</p>{lines}<p>{last}</p></main></body></html>"


@pytest.mark.parametrize(
    ("change", "shown"),
    [(("Prix : 45 €", "Fin"), "- Prix : 59 €\n+ Prix : 45 €"), (("Prix : 59 €", "Fin modifiée"), "further down")],
    ids=["at-the-top", "past-what-is-kept"],
)
async def test_a_long_page_shows_only_what_changed(
    web: respx.MockRouter, tmp_path: Path, change: tuple[str, str], shown: str
) -> None:
    route = web.get(URL).respond(200, html=long_page("Prix : 59 €", "Fin"))
    async with page_source(tmp_path / "pages") as source:
        route.respond(200, html=long_page(*change))
        (item,) = await taken(source, wait_s=1.0)  # reading and comparing a long page takes a while on a busy machine
    changes = item.body.partition("(- before, + now):\n")[2]
    assert changes == shown or (shown == "further down" and shown in changes and "+ " not in changes)


async def test_a_changed_line_that_starts_like_a_diff_header_is_shown(web: respx.MockRouter, tmp_path: Path) -> None:
    route = web.get(URL).respond(200, html=lamp("59 €").replace("En stock", "++ En stock"))
    async with page_source(tmp_path / "pages") as source:
        route.respond(200, html=lamp("59 €").replace("En stock", "++ Rupture"))
        (item,) = await taken(source)
    assert "- ++ En stock\n+ ++ Rupture" in item.body


async def test_a_reader_that_fails_does_not_stop_the_source(web: respx.MockRouter, tmp_path: Path) -> None:
    class Failing(FileReader):
        broken = False

        async def read(self, data: bytes, media_type: str) -> str | None:
            if self.broken:
                raise RuntimeError("a bug in the reader")
            return await super().read(data, media_type)

    reader = Failing()
    route = web.get(URL).respond(200, html=lamp("59 €"))
    source = PageSource(
        "pages", [Watched("la lampe", URL)], PublicWeb(accept=PAGES), tmp_path / "pages", every_s=0.01, reader=reader
    )
    async with source:
        reader.broken = True
        assert await taken(source) == []
        reader.broken = False
        route.respond(200, html=lamp("45 €"))
        assert len(await taken(source)) == 1

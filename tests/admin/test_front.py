"""The web front served by the admin: its assets cached for good, every other page its `index.html`,
and a page that says how to build it when it is not built."""

from pathlib import Path

import pytest

from .harness import Harness

INDEX = '<!doctype html><div id="root"></div><script type="module" src="/assets/app-3f2a1c.js"></script>'


@pytest.fixture
def built(tmp_path: Path) -> Path:
    front = tmp_path / "front"
    (front / "assets").mkdir(parents=True)
    (front / "index.html").write_text(INDEX)
    (front / "assets" / "app-3f2a1c.js").write_text("console.log('nestor')")
    (front / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside the build")
    return front


async def test_every_page_of_the_front_is_its_index(tmp_path: Path, built: Path) -> None:
    async with Harness(tmp_path, front_dir=built) as admin:
        for path in ("/invitation", "/accounts/abc123", "/settings/profile"):
            response = await admin.browser.get(path)
            assert response.status_code == 200 and response.text == INDEX, path
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert (await admin.browser.get("/favicon.svg")).text == "<svg/>"


async def test_assets_are_cached_for_good_and_never_read_outside_the_build(tmp_path: Path, built: Path) -> None:
    async with Harness(tmp_path, front_dir=built) as admin:
        asset = await admin.browser.get("/assets/app-3f2a1c.js")
        assert asset.status_code == 200 and asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert (await admin.browser.get("/assets/gone-0000.js")).status_code == 404
        for sneaky in ("/assets/..%2F..%2Fsecret.txt", "/..%2Fsecret.txt"):
            response = await admin.browser.get(sneaky)
            assert "outside the build" not in response.text, sneaky


async def test_without_a_build_a_page_says_how_to_make_one(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        response = await admin.browser.get("/invitation")
        assert response.status_code == 503 and "pnpm build" in response.text
        assert (await admin.browser.get("/health")).json() == {"status": "ok"}


async def test_an_unknown_api_address_is_never_the_front(tmp_path: Path, built: Path) -> None:
    async with Harness(tmp_path, front_dir=built) as admin:
        response = await admin.browser.get("/api/v2/journal")
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"

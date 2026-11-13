"""Webhooks as watch items: a post signed with its hook's secret (or bearing it) is an item of the hook's kind, kept
until taken across a restart; a post without the secret, too large, not JSON or to an unknown hook is refused and
yields nothing. Posts reach the source's app in process."""

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterable
from pathlib import Path

import httpx
import pytest

from nestor.adapters.common.http import signature
from nestor.adapters.common.state import StateFile
from nestor.adapters.inbound.webhook import Hook, WebhookSource, plugin
from nestor.core import ContractError, ProviderError
from nestor.core.i18n import Locale
from nestor.runtime import Services
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.initiative import InboundEventSourceContract

SECRET = "s3cret"
GITHUB = Hook(name="github", kind="github", secret=SECRET)
RELEASE = {"action": "published", "release": {"tag_name": "v7.0.0", "name": "Nestor 7"}}


def webhook_source(state: Path, *hooks: Hook, max_bytes: int = 65_536) -> WebhookSource:
    return WebhookSource("webhooks", hooks or (GITHUB,), StateFile(state), port=0, max_bytes=max_bytes)


async def post(
    source: WebhookSource, body: bytes | Iterable[bytes], headers: dict[str, str] | None = None, hook: str = "github"
) -> httpx.Response:
    """`body` in chunks is sent without its length, as a stream."""
    content = body if isinstance(body, bytes) else _streamed(body)
    transport = httpx.ASGITransport(app=source.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://nestor") as client:
        return await client.post(f"/hooks/{hook}", content=content, headers=headers or {})


async def _streamed(chunks: Iterable[bytes]) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def signed(body: bytes, secret: str = SECRET) -> dict[str, str]:
    return {"X-Hub-Signature-256": signature(secret, body), "X-GitHub-Event": "release"}


async def taken(source: WebhookSource, wait_s: float = 0.05) -> list[str]:
    found: list[str] = []

    async def take() -> None:
        async for item in source.items():
            found.append(item.title)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(take(), wait_s)
    return found


class TestWebhookSource(InboundEventSourceContract):
    pushed = True

    @pytest.fixture(autouse=True)
    def folder(self, tmp_path: Path) -> None:
        self.state = tmp_path / "webhooks.json"

    def source(self) -> WebhookSource:
        self.current = webhook_source(self.state)
        return self.current

    async def arrive(self, title: str) -> None:
        body = json.dumps({"title": title}).encode()
        assert (await post(self.current, body, {"Authorization": f"Bearer {SECRET}"})).status_code == 202


async def test_a_signed_post_is_an_item_of_its_hook_s_kind(tmp_path: Path) -> None:
    body = json.dumps(RELEASE).encode()
    async with webhook_source(tmp_path / "w.json") as source:
        assert (await post(source, body, signed(body))).status_code == 202
        item = await anext(source.items())
    assert (item.kind, item.sender, item.title) == ("github", "github", "release · published")
    assert '"tag_name": "v7.0.0"' in item.body


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        (signed(b'{"x": 1}', secret="wrong"), b'{"x": 1}'),
        (signed(b'{"x": 1}'), b'{"x": 2}'),  # signed, then altered
        ({"Authorization": "Bearer wrong"}, b'{"x": 1}'),
        ({}, b'{"x": 1}'),
    ],
    ids=["bad-signature", "altered-body", "bad-token", "no-proof"],
)
async def test_a_post_without_its_hook_s_secret_is_refused(tmp_path: Path, headers: dict, body: bytes) -> None:
    async with webhook_source(tmp_path / "w.json") as source:
        assert (await post(source, body, headers)).status_code == 401
        assert await taken(source) == []


@pytest.mark.parametrize(
    ("body", "hook", "status"),
    [
        (b"x" * 2_000, "github", 413),
        ([b"x" * 600, b"x" * 600], "github", 413),
        (b"not json", "github", 400),
        (b"{}", "unknown", 404),
    ],
    ids=["too-large", "too-large-without-length", "not-json", "unknown-hook"],
)
async def test_a_post_that_cannot_be_taken_is_refused(
    tmp_path: Path, body: bytes | list[bytes], hook: str, status: int
) -> None:
    async with webhook_source(tmp_path / "w.json", max_bytes=1_000) as source:
        response = await post(source, body, {"Authorization": f"Bearer {SECRET}"}, hook=hook)
        assert response.status_code == status
        assert await taken(source) == []


async def test_each_hook_has_its_own_secret_and_kind(tmp_path: Path) -> None:
    washer = Hook(name="washer", kind="washing-machine", secret="other")
    async with webhook_source(tmp_path / "w.json", GITHUB, washer) as source:
        assert source.kinds == ("github", "washing-machine")
        assert (await post(source, b"{}", {"Authorization": f"Bearer {SECRET}"}, hook="washer")).status_code == 401
        body = b'{"title": "Cycle fini"}'
        assert (await post(source, body, {"Authorization": "Bearer other"}, hook="washer")).status_code == 202
        assert (await anext(source.items())).kind == "washing-machine"


def test_two_hooks_of_one_name_are_refused_by_the_configuration(tmp_path: Path) -> None:
    hook = {"name": "github", "kind": "github", "secret": SECRET}
    services = Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("en"))
    with pytest.raises(ContractError, match="same name"):
        plugin.create({"hooks": [hook, hook]}, "webhooks", services)


async def test_a_port_already_taken_fails_the_start_clearly(tmp_path: Path) -> None:
    with socket.socket() as taken_port:
        taken_port.bind(("127.0.0.1", 0))
        taken_port.listen()
        port = taken_port.getsockname()[1]
        source = WebhookSource("webhooks", (GITHUB,), StateFile(tmp_path / "w.json"), port=port)
        with pytest.raises(ProviderError, match=f"cannot listen on 127.0.0.1:{port}"):
            await source.start()


async def test_a_post_whose_handling_was_cut_short_comes_again_after_a_restart(tmp_path: Path) -> None:
    bearer = {"Authorization": f"Bearer {SECRET}"}
    async with webhook_source(tmp_path / "w.json") as source:
        assert (await post(source, b'{"title": "un"}', bearer)).status_code == 202
        items = source.items()
        assert (await anext(items)).title == "un"
        await items.aclose()  # stopped during its triage: the next one was never asked for
    async with webhook_source(tmp_path / "w.json") as restarted:
        assert await taken(restarted) == ["un"]

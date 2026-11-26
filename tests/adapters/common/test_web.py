"""The public web client against DNS rebinding: a name public when it is checked and local when it is fetched never
reaches the household's network, a real server listening there."""

import asyncio
import socket
import time
from collections.abc import AsyncIterator

import pytest

from nestor.adapters.common.web import PAGES, PublicWeb, WebError


@pytest.fixture
async def household_server() -> AsyncIterator[tuple[int, list[str]]]:
    """A server on the household's network (loopback here): its port, and the requests it received."""
    received: list[str] = []

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        received.append((await reader.readline()).decode())
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 13\r\n\r\n<p>router</p>")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    async with server:
        yield server.sockets[0].getsockname()[1], received


async def test_a_name_that_turns_local_once_checked_reaches_nothing(
    monkeypatch: pytest.MonkeyPatch, household_server: tuple[int, list[str]]
) -> None:
    port, received = household_server
    answers = iter(["1.1.1.1"])  # public for the check, the household's own address for every lookup after

    def rebinding(host: str | bytes, port: int | None, *args: object, **kwargs: object) -> list:
        name = host.decode() if isinstance(host, bytes) else host  # the event loop passes text, anyio bytes
        address = next(answers, "127.0.0.1") if name == "rebind.example" else name
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 80))]

    monkeypatch.setattr(socket, "getaddrinfo", rebinding)
    web = PublicWeb(accept=PAGES, timeout_s=2)
    with pytest.raises(WebError):
        await web.get(f"http://rebind.example:{port}/")
    await web.aclose()
    assert received == [], "the household's server was never asked"


async def test_a_name_that_never_resolves_fails_within_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def stuck(host: str | bytes, *args: object, **kwargs: object) -> list:
        time.sleep(1)  # a resolver that does not answer
        raise socket.gaierror("no answer")

    monkeypatch.setattr(socket, "getaddrinfo", stuck)
    web = PublicWeb(accept=PAGES, timeout_s=0.1)
    started = time.monotonic()
    with pytest.raises(WebError, match="could not be found"):
        await web.get("https://stuck.example/")
    await web.aclose()
    assert time.monotonic() - started < 0.5

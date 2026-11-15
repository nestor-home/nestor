"""A public MCP server's tool called over HTTP: its answer in JSON or as events, its failures as transient errors."""

import httpx
import pytest
import respx

from nestor.adapters.tools.public_mcp import PublicMcpServer
from nestor.core import ProviderError

from .mcp_answers import answered, events

URL = "https://mcp.example.org/mcp"


@pytest.mark.parametrize("answer", [events("found"), answered("found")], ids=["events", "json"])
async def test_the_tool_s_text_is_its_answer(api: respx.MockRouter, answer: httpx.Response) -> None:
    api.post(URL).respond(answer.status_code, content=answer.content, headers=answer.headers)
    server = PublicMcpServer("example", URL)
    assert await server.call("search", {"query": "q"}) == "found"
    await server.aclose()


@pytest.mark.parametrize(
    ("answer", "says"),
    [
        (events("Rate limit exceeded", error=True), "Rate limit exceeded"),
        (httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "busy"}}), "busy"),
        (httpx.Response(200, text="<html>maintenance</html>"), "not MCP"),
    ],
    ids=["tool error", "json-rpc error", "not mcp"],
)
async def test_a_tool_that_fails_is_a_transient_error(api: respx.MockRouter, answer: httpx.Response, says: str) -> None:
    api.post(URL).respond(answer.status_code, content=answer.content, headers=answer.headers)
    server = PublicMcpServer("example", URL)
    with pytest.raises(ProviderError, match=says) as failed:
        await server.call("search", {"query": "q"})
    assert failed.value.transient
    await server.aclose()

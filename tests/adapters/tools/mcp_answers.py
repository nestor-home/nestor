"""How a public MCP server answers a `tools/call`: in JSON, or as server-sent events."""

import json

import httpx


def called(request: httpx.Request) -> tuple[str, dict]:
    """The tool a `tools/call` asks for, and its arguments."""
    call = json.loads(request.content)
    assert call["method"] == "tools/call"
    assert "text/event-stream" in request.headers["Accept"], "MCP servers may answer in events"
    return call["params"]["name"], call["params"]["arguments"]


def events(text: str, *, error: bool = False) -> httpx.Response:
    envelope = {"result": {"content": [{"type": "text", "text": text}], **({"isError": True} if error else {})}}
    body = f"event: message\ndata: {json.dumps(envelope, ensure_ascii=False)}\n\n".encode()
    return httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"})


def answered(text: str) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": text}]}})

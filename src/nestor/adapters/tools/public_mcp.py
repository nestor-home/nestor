"""A tool of a public MCP server called over plain HTTP, without a session: one JSON-RPC `tools/call`, answered in
JSON or as server-sent events, whose text is the tool's answer. Exa's and Parallel's searches are served this way."""

import json
import re
from collections.abc import Mapping
from typing import Any

from nestor.adapters.common.http import HttpApi

EVENT_LINES = re.compile(r"\r\n|\r|\n")  # SSE's line ends only: page text may hold U+2028 and the like


class PublicMcpServer(HttpApi):
    def __init__(self, provider: str, url: str, *, headers: Mapping[str, str] | None = None, **kwargs: Any) -> None:
        self._url = url  # called as it is: a base address would gain a trailing slash
        accepts = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        super().__init__(provider, headers={**accepts, **(headers or {})}, **kwargs)

    async def call(self, tool: str, arguments: Mapping[str, object]) -> str:
        """The text the tool answered; a transient `ProviderError` for a JSON-RPC error or a tool that failed (a free
        tier's limit is one)."""
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": dict(arguments)},
        }
        response = await self.request("POST", self._url, json=body)
        text = response.content.decode(response.charset_encoding or "utf-8", errors="replace")
        for payload in [text.strip(), *(line[6:] for line in EVENT_LINES.split(text) if line.startswith("data: "))]:
            if not payload.startswith("{"):
                continue
            try:
                envelope = json.loads(payload)
            except ValueError:
                continue
            if error := envelope.get("error"):
                raise self.error(f"{tool}: {error.get('message') or error}", transient=True)
            result = envelope.get("result") or {}
            said = " ".join(c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict)).strip()
            if result.get("isError"):
                raise self.error(f"{tool}: {said or 'the tool failed'}", transient=True)
            return said
        raise self.error(f"{tool}: an answer that is not MCP", transient=True)

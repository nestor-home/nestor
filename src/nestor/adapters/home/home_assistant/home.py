"""Home Assistant as the household's home: its presence (WebSocket API) and, unless it has none, the MCP server of its
actions."""

import asyncio

from nestor.adapters.home.home_assistant.presence import HomeAssistantPresence
from nestor.adapters.tools.mcp.provider import McpToolProvider
from nestor.core import Component, Health
from nestor.core.i18n import Message
from nestor.modules.home import Home, HomeOverview


class HomeAssistant(Home):
    """Starts and closes its presence source and its tools together. Unavailable while neither answers, degraded
    while only one does; the presence source's refused token fails `start`, as the MCP server's does. Without tools
    (presence only), its presence alone tells its health."""

    brand = "homeassistant"

    def __init__(self, name: str, presence: HomeAssistantPresence, tools: McpToolProvider | None) -> None:
        self.name = name
        self._presence, self._tools = presence, tools

    @property
    def presence(self) -> HomeAssistantPresence:
        return self._presence

    @property
    def tools(self) -> McpToolProvider | None:
        return self._tools

    @property
    def _parts(self) -> tuple[Component, ...]:
        return (self._presence,) if self._tools is None else (self._presence, self._tools)

    def overview(self) -> HomeOverview:
        return self._presence.overview()

    def room_of(self, label: str) -> str | None:
        return self._presence.room_of(label)

    def details(self) -> dict[str, str]:
        tools = {} if self._tools is None else {"tools": str(len(self._tools.tools()))}
        return {"granularity": self._presence.granularity, **tools}

    def health(self) -> Health:
        up = [part.health() is Health.STARTED for part in self._parts]
        return Health.STARTED if all(up) else Health.DEGRADED if any(up) else Health.UNAVAILABLE

    def health_detail(self) -> Message | None:
        return next((detail for part in self._parts if (detail := part.health_detail())), None)

    async def start(self) -> None:
        """Both connections at once: neither waits for the other's timeout. One refused closes the other."""
        failures = [
            outcome
            for outcome in await asyncio.gather(*(part.start() for part in self._parts), return_exceptions=True)
            if isinstance(outcome, BaseException)
        ]
        if failures:
            await self.close()
            raise failures[0]

    async def close(self) -> None:
        for part in reversed(self._parts):
            await part.close()

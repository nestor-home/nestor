"""Home Assistant as the household's home: one address and one token for its presence (WebSocket API) and its
actions (its MCP server, Assist's tools)."""

import asyncio

from nestor.adapters.home.home_assistant.presence import HomeAssistantPresence
from nestor.adapters.tools.mcp import McpToolProvider
from nestor.core import Health
from nestor.core.i18n import Message
from nestor.modules.home import Home, HomeOverview


class HomeAssistant(Home):
    """Starts and closes its presence source and its tools together. Unavailable while neither answers, degraded
    while only one does; the presence source's refused token fails `start`, as the MCP server's does."""

    brand = "homeassistant"

    def __init__(self, name: str, presence: HomeAssistantPresence, tools: McpToolProvider) -> None:
        self.name = name
        self._presence, self._tools = presence, tools

    @property
    def presence(self) -> HomeAssistantPresence:
        return self._presence

    @property
    def tools(self) -> McpToolProvider:
        return self._tools

    def overview(self) -> HomeOverview:
        return self._presence.overview()

    def room_of(self, label: str) -> str | None:
        return self._presence.room_of(label)

    def details(self) -> dict[str, str]:
        return {"granularity": self._presence.granularity, "tools": str(len(self._tools.tools()))}

    def health(self) -> Health:
        up = [part.health() is Health.STARTED for part in (self._presence, self._tools)]
        return Health.STARTED if all(up) else Health.DEGRADED if any(up) else Health.UNAVAILABLE

    def health_detail(self) -> Message | None:
        return self._presence.health_detail() or self._tools.health_detail()

    async def start(self) -> None:
        """Both connections at once: neither waits for the other's timeout. One refused closes the other."""
        failures = [
            outcome
            for outcome in await asyncio.gather(self._presence.start(), self._tools.start(), return_exceptions=True)
            if isinstance(outcome, BaseException)
        ]
        if failures:
            await self.close()
            raise failures[0]

    async def close(self) -> None:
        await self._tools.close()
        await self._presence.close()

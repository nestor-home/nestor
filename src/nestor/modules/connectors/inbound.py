"""One inbound source over every connected account that can feed watches (each mailbox…).

Connections plugged in or removed while Nestor runs are followed or dropped without a restart.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Mapping

from nestor.modules.connectors.events import ConnectionChanged, ConnectionCreated, ConnectionRemoved
from nestor.modules.connectors.service import Connections
from nestor.modules.connectors.types import Connection, Status
from nestor.modules.initiative import InboundEventSource, Incoming
from nestor.modules.journal import Subscription

log = logging.getLogger(__name__)


class ConnectedInbound(InboundEventSource):
    name = "connected-inbound"

    def __init__(self, connections: Connections) -> None:
        self.connections = connections
        self.kinds = tuple(sorted({k for c in connections.connectors.values() for k in c.info.inbound}))
        self._feeds: dict[str, asyncio.Task[None]] = {}
        self._queue: asyncio.Queue[Incoming] = asyncio.Queue()

    async def items(self) -> AsyncGenerator[Incoming]:
        changes = self.connections.journal.subscribe(ConnectionCreated, ConnectionChanged, ConnectionRemoved)
        watcher = asyncio.create_task(self._follow_changes(changes))
        self._sync(self.connections.connections)
        try:
            while True:
                yield await self._queue.get()
        finally:
            changes.close()
            watcher.cancel()
            for feed in list(self._feeds.values()):
                feed.cancel()
            await asyncio.gather(watcher, *self._feeds.values(), return_exceptions=True)
            self._feeds.clear()

    async def _follow_changes(self, changes: Subscription) -> None:
        async for _ in changes:
            self._sync(self.connections.connections)

    def _sync(self, connections: Mapping[str, Connection]) -> None:
        wanted = {cid for cid, c in connections.items() if c.status is Status.CONNECTED}
        for cid in list(self._feeds):
            if cid not in wanted:
                self._feeds.pop(cid).cancel()
        for cid in wanted - set(self._feeds):
            connection = connections[cid]
            connector = self.connections.connectors.get(connection.kind)
            source = connector.inbound(connection, self.connections.access(connection)) if connector else None
            if source is not None:
                self._feeds[cid] = asyncio.create_task(self._pump(source), name=f"inbound {cid}")

    async def _pump(self, source: InboundEventSource) -> None:
        try:
            async with source:
                async for item in source.items():
                    self._queue.put_nowait(item)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("inbound source %s stopped", source.name)
        finally:
            with contextlib.suppress(Exception):
                await source.close()

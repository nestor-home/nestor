"""The presence source: a live view of a Home Assistant installation over its WebSocket API."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from pydantic import ValidationError

from nestor.adapters.home.home_assistant.client import (
    AuthenticationRejected,
    HomeAssistantSession,
    SessionLost,
    websocket_url,
)
from nestor.adapters.home.home_assistant.installation import (
    AREAS,
    DEVICES,
    ENTITIES,
    STATES,
    Installation,
    PresenceMapping,
    StateChanged,
    parse,
)
from nestor.core import Health, ProviderError
from nestor.modules.home import Granularity, Presence, PresenceSource, Whereabouts

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Live:
    """A connected session and the installation it keeps current."""

    session: HomeAssistantSession
    installation: Installation

    async def follow(self) -> None:
        """Applies `state_changed` events until the session breaks (`SessionLost`)."""
        async for event in self.session.events():
            try:
                change = StateChanged.model_validate(event)
            except ValidationError:
                logger.warning("malformed state_changed event ignored: %.200s", event)
                continue
            self.installation.apply(change)


class HomeAssistantPresence(PresenceSource):
    """Relays Home Assistant's presence at the finest granularity the installation offers.

    `start` connects, reads the area, device and entity registries, subscribes to `state_changed`
    and reads every state; a background task then follows the events. A refused token fails `start`
    (`ProviderError`, not transient). An unreachable Home Assistant does not: presence is optional
    to the assistant, so the source starts disconnected and keeps retrying. Whenever it is not
    connected, everyone is unknown. A dropped connection is retried at once, then with a doubling
    delay from `reconnect_min_s` up to `reconnect_max_s`; a token refused on reconnection stops the
    retries (Home Assistant may ban an address after repeated failed logins).

    Registries are read once per connection: an area or entity added later is seen after the next
    reconnection.
    """

    name = "home-assistant"
    brand = "homeassistant"

    def __init__(
        self,
        base_url: str,
        token: str,
        mapping: PresenceMapping,
        *,
        sync_timeout_s: float = 30.0,
        reconnect_min_s: float = 1.0,
        reconnect_max_s: float = 60.0,
    ) -> None:
        self._url, self._token, self._mapping = websocket_url(base_url), token, mapping
        self._sync_timeout_s, self._reconnect_min_s, self._reconnect_max_s = (
            sync_timeout_s,
            reconnect_min_s,
            reconnect_max_s,
        )
        self._granularity = Granularity.HOME
        self._installation: Installation | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def granularity(self) -> Granularity:
        return self._granularity

    def health(self) -> Health:
        """Unavailable while disconnected: everyone is unknown until it reconnects."""
        return Health.STARTED if self._installation is not None else Health.UNAVAILABLE

    def presence(self) -> Presence:
        if self._installation is None:
            unknown = dict.fromkeys(self._mapping.people, Whereabouts())
            return Presence(granularity=self._granularity, people=unknown)
        return self._installation.presence()

    async def start(self) -> None:
        if self._task is not None:
            return
        live = None
        try:
            live = await self._connect()
        except AuthenticationRejected as error:
            raise ProviderError(self.name, f"access token refused: {error}", transient=False) from None
        except SessionLost as error:
            logger.warning("%s: Home Assistant unavailable, presence unknown until it is: %s", self.name, error)
        self._task = asyncio.create_task(self._run(live), name=f"{self.name}-events")

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._installation = None

    async def _connect(self) -> _Live:
        """Opens a session and fills the view from it; raises `SessionLost` or `AuthenticationRejected`."""
        try:
            async with asyncio.timeout(self._sync_timeout_s):
                session = await HomeAssistantSession.open(self._url, self._token)
                try:
                    installation = await self._sync(session)
                except BaseException:
                    await session.close()
                    raise
        except TimeoutError:
            raise SessionLost(f"no answer within {self._sync_timeout_s}s") from None
        self._installation, self._granularity = installation, installation.granularity
        if unplaced := installation.unplaced_sensors:
            logger.warning("%s: occupancy sensors without an area, ignored: %s", self.name, ", ".join(unplaced))
        logger.info("%s: connected, presence granularity %s", self.name, self._granularity.name)
        return _Live(session, installation)

    async def _sync(self, session: HomeAssistantSession) -> Installation:
        areas = parse(AREAS, await session.command("config/area_registry/list"), "area registry")
        devices = parse(DEVICES, await session.command("config/device_registry/list"), "device registry")
        entities = parse(ENTITIES, await session.command("config/entity_registry/list"), "entity registry")
        await session.subscribe("state_changed")  # before the snapshot, so no change falls in between
        states = parse(STATES, await session.command("get_states"), "states")
        return Installation(self._mapping, areas=areas, devices=devices, entities=entities, states=states)

    async def _run(self, live: _Live | None) -> None:
        delay = self._reconnect_min_s
        while True:
            if live is None:
                try:
                    live = await self._connect()
                except AuthenticationRejected as error:
                    logger.error("%s: access token refused, no more reconnection: %s", self.name, error)
                    return
                except SessionLost as error:
                    logger.warning("%s: still unavailable, next attempt in %.1fs: %s", self.name, delay, error)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self._reconnect_max_s)
                    continue
            delay = self._reconnect_min_s
            try:
                await live.follow()
            except SessionLost as error:
                logger.warning("%s: connection lost, presence unknown until it is back: %s", self.name, error)
            finally:
                self._installation = None
                await live.session.close()
            live = None

"""The presence source: a live view of a Home Assistant installation over its WebSocket API."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, replace

from pydantic import ValidationError

from nestor.adapters.common.availability import Availability
from nestor.adapters.home.home_assistant.client import (
    AuthenticationRejected,
    HomeAssistantSession,
    SessionLost,
    websocket_url,
)
from nestor.adapters.home.home_assistant.installation import (
    AREAS,
    ASSISTANT,
    DEVICES,
    ENTITIES,
    ENTRIES,
    EXPOSURE,
    FLOORS,
    STATES,
    Installation,
    PresenceMapping,
    Registries,
    StateChanged,
    parse,
)
from nestor.adapters.home.home_assistant.layout import Covers
from nestor.core import Health, ProviderError
from nestor.core.i18n import Message
from nestor.modules.home import Granularity, HomeOverview, Presence, PresenceSource, Whereabouts

logger = logging.getLogger(__name__)

STATE_CHANGED = "state_changed"
# what changes the rooms, what sits in them or what is shown to the assistant (an exposure is an entity's option)
REGISTRY_UPDATED = frozenset(
    {"floor_registry_updated", "area_registry_updated", "device_registry_updated", "entity_registry_updated"}
)


def _nobody(domain: str, device_class: str | None, name: str) -> bool:
    return False


async def _registries(session: HomeAssistantSession) -> Registries:
    """Every registry and what is exposed to Assist, each with its whole entry. Floors and what is exposed are only for
    the map: a version without floors, or a token not allowed to read what is exposed, leaves it without them."""
    areas = parse(AREAS, await session.command("config/area_registry/list"), "area registry")
    devices = parse(DEVICES, await session.command("config/device_registry/list"), "device registry")
    entities = parse(ENTITIES, await session.command("config/entity_registry/list"), "entity registry")
    floors = await session.ask("config/floor_registry/list")
    exposure = await session.ask("homeassistant/expose_entity/list")
    if exposure is None:
        logger.warning("home: Home Assistant does not say what it exposes to Assist (an admin's token?): no devices")
    exposed = parse(EXPOSURE, exposure, "exposed entities").to(ASSISTANT) if exposure is not None else []
    entries = await session.ask("config/entity_registry/get_entries", entity_ids=exposed) if exposed else None
    found = parse(ENTRIES, entries, "entries") if entries is not None else {}
    return Registries(
        floors=tuple(parse(FLOORS, floors, "floor registry")) if floors is not None else (),
        areas=tuple(areas),
        devices=tuple(devices),
        entities=tuple(entities),
        exposed={entity: found.get(entity) for entity in exposed},
    )


@dataclass(frozen=True, slots=True)
class _Live:
    """A connected session and the installation it keeps current."""

    session: HomeAssistantSession
    installation: Installation

    async def follow(self) -> None:
        """Applies `state_changed` events, and reads the registries again when one changes, until the session breaks
        (`SessionLost`)."""
        async for event in self.session.events():
            kind = event.get("event_type")
            if kind in REGISTRY_UPDATED:  # a burst of them (an integration reloading) is read once
                self.session.drop_queued(REGISTRY_UPDATED)  # read below; what comes meanwhile is read again after
                self.installation.relist(await _registries(self.session))
                continue
            if kind != STATE_CHANGED:
                continue
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

    Registries are read at each connection and again whenever one of them changes (a room renamed, a device moved,
    an entity exposed to Assist or no longer): the rooms and what the installation shows its assistant stay current.
    `covers`: whether acting on an entity needs the person's go-ahead, to mark the devices that do.
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
        covers: Covers = _nobody,
    ) -> None:
        self._url, self._token, self._mapping, self._covers = websocket_url(base_url), token, mapping, covers
        self._sync_timeout_s, self._reconnect_min_s, self._reconnect_max_s = (
            sync_timeout_s,
            reconnect_min_s,
            reconnect_max_s,
        )
        self._granularity = Granularity.HOME
        self._installation: Installation | None = None
        self._last: Installation | None = None  # the last one connected: its rooms and devices, while it reconnects
        self._task: asyncio.Task[None] | None = None
        self._availability = Availability(logger, lambda: self.name, "presence unknown until it answers")

    @property
    def granularity(self) -> Granularity:
        """The installation's, as its sensors are now; the last known while disconnected."""
        if self._installation is not None:
            self._granularity = self._installation.granularity
        return self._granularity

    def health(self) -> Health:
        """Unavailable while disconnected: everyone is unknown until it reconnects."""
        return Health.STARTED if self._installation is not None else Health.UNAVAILABLE

    def health_detail(self) -> Message | None:
        return None if self._installation is not None else Message.of("health-home-assistant-disconnected")

    def overview(self) -> HomeOverview:
        """What the live view shows of the installation; disconnected, how the household is tied to it and the rooms
        and devices last known (Home Assistant restarting does not empty the house), nobody placed in them."""
        installation = self._installation
        people, trackers = dict(self._mapping.people), dict(self._mapping.rooms)
        if installation is None:
            last = self._last
            return HomeOverview(
                connected=False,
                granularity=self._granularity,
                rooms=tuple(replace(room, occupied=None) for room in last.rooms()) if last else (),
                devices=last.devices() if last else (),
                people=people,
                trackers=trackers,
            )
        return HomeOverview(
            connected=True,
            granularity=installation.granularity,
            rooms=installation.rooms(),
            residents=installation.residents(),
            people=people,
            trackers=trackers,
            unplaced_sensors=tuple(installation.unplaced_sensors),
            devices=installation.devices(),
        )

    def room_of(self, label: str) -> str | None:
        return self._installation.room_of(label) if self._installation is not None else None

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
            self._availability.lost(error)
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
        self._installation, self._last, self._granularity = installation, installation, installation.granularity
        if unplaced := installation.unplaced_sensors:
            logger.warning("%s: occupancy sensors without an area, ignored: %s", self.name, ", ".join(unplaced))
        if not self._availability.back(f"presence granularity {self._granularity}"):
            logger.info("%s: connected, presence granularity %s", self.name, self._granularity)
        return _Live(session, installation)

    async def _sync(self, session: HomeAssistantSession) -> Installation:
        await session.subscribe(STATE_CHANGED)  # before reading, so no change falls in between
        for kind in sorted(REGISTRY_UPDATED):  # only for the map: a token or a version that refuses one goes without
            await session.ask("subscribe_events", event_type=kind)
        registries = await _registries(session)
        states = parse(STATES, await session.command("get_states"), "states")
        return Installation(self._mapping, registries, states=states, covers=self._covers)

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
                    self._availability.lost(error)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self._reconnect_max_s)
                    continue
            delay = self._reconnect_min_s
            try:
                await live.follow()
            except SessionLost as error:
                self._availability.lost(error)
            finally:
                self._installation = None
                await live.session.close()
            live = None

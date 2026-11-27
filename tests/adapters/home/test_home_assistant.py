"""Home Assistant presence: the presence contract against a fake Home Assistant WebSocket API, then
the mapping rules, live updates and what only a network service can break (drops, refusals, silence)."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from nestor.adapters.home.home_assistant import (
    HomeAssistant,
    HomeAssistantPresence,
    HomeAssistantSettings,
    PresenceMapping,
    plugin,
)
from nestor.adapters.home.home_assistant.client import websocket_url
from nestor.core import ContractError, Health, PersonId, ProviderError
from nestor.core.i18n import Locale
from nestor.modules.cognition.tools import Risk
from nestor.modules.home import Device, Granularity, Presence, Resident, Room, Whereabouts
from nestor.runtime import Services
from nestor.testing.home import PresenceSourceContract
from nestor.testing.i18n import EchoLocalizer

from ..served import Served, bearer

TOKEN = "eyJhbGciOiJIUzI1NiJ9.long-lived-test-token.c2lnbmF0dXJl"
ALICE, BOB = PersonId("alice"), PersonId("bob")
EPOCH = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)


def area(area_id: str, name: str, *aliases: str) -> dict[str, Any]:
    return {
        "aliases": list(aliases),
        "area_id": area_id,
        "floor_id": None,
        "icon": None,
        "labels": [],
        "name": name,
        "picture": None,
        "created_at": 0.0,
        "modified_at": 0.0,
    }


def device(device_id: str, area_id: str | None, name: str | None = None) -> dict[str, Any]:
    return {
        "area_id": area_id,
        "config_entries": ["01JCONFIGENTRY"],
        "id": device_id,
        "manufacturer": "Aqara",
        "model": "RTCGQ11LM",
        "name": name or f"Device {device_id}",
        "name_by_user": None,
        "disabled_by": None,
    }


def entity(entity_id: str, *, area_id: str | None = None, device_id: str | None = None) -> dict[str, Any]:
    return {
        "area_id": area_id,
        "categories": {},
        "config_entry_id": "01JCONFIGENTRY",
        "device_id": device_id,
        "disabled_by": None,
        "entity_category": None,
        "entity_id": entity_id,
        "has_entity_name": True,
        "hidden_by": None,
        "icon": None,
        "id": f"id-{entity_id}",
        "labels": [],
        "name": None,
        "original_name": None,
        "platform": "zha",
        "translation_key": None,
        "unique_id": f"uid-{entity_id}",
        "options": {"conversation": {"should_expose": False}},
    }


class FakeHomeAssistant:
    """Plays Home Assistant's WebSocket API: the auth handshake, registry lists, `get_states` and
    `state_changed` subscriptions, with the payload shapes of a real installation."""

    def __init__(self) -> None:
        self.token = TOKEN
        self.areas = [area("living_room", "Living Room", "Salon"), area("kitchen", "Kitchen"), area("office", "Office")]
        self.floors: list[dict[str, Any]] = []
        self.devices: list[dict[str, Any]] = []
        self.entities: list[dict[str, Any]] = []
        self.exposed: dict[str, dict[str, bool]] = {}  # entity id → assistant → exposed
        self.aliases: dict[str, list[str | None]] = {}  # entity id → its registry aliases
        self.states: dict[str, dict[str, Any]] = {}
        self.available = True  # False: connections are closed before the handshake
        self.silent = False  # True: connections are accepted but never answered
        self.refused: set[str] = set()  # commands answered with an error
        self.refused_events: set[str] = set()  # event types it will not let a client subscribe to
        self.malformed: set[str] = set()  # commands answered with a payload that is not Home Assistant's
        self.before_snapshot: list[dict[str, Any]] = []  # events fired between `subscribe_events` and `get_states`
        self.chatter = False  # True: messages of unknown types are sent between replies
        self.attempts = 0
        self._clock = EPOCH
        self._subscribers: dict[ServerConnection, dict[str, int]] = {}  # connection → event type → subscription
        self._server: Server | None = None

    async def __aenter__(self) -> "FakeHomeAssistant":
        self._server = await serve(self._handle, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = next(iter(self._server.sockets)).getsockname()[:2]
        return f"http://{host}:{port}"

    def source(self, mapping: PresenceMapping, **options: Any) -> HomeAssistantPresence:
        options = {"reconnect_min_s": 0.01, "reconnect_max_s": 0.05, "sync_timeout_s": 1.0, **options}
        return HomeAssistantPresence(self.url, TOKEN, mapping, **options)

    def state(self, entity_id: str, value: str, **attributes: Any) -> dict[str, Any]:
        """Sets an entity's state before a connection reads it, and returns it."""
        self._clock += timedelta(seconds=1)
        stamp = self._clock.isoformat()
        attributes.setdefault("friendly_name", entity_id.split(".", 1)[1].replace("_", " ").title())
        state = {
            "entity_id": entity_id,
            "state": value,
            "attributes": attributes,
            "last_changed": stamp,
            "last_reported": stamp,
            "last_updated": stamp,
            "context": {"id": f"01JCTX{self._clock.timestamp():.0f}", "parent_id": None, "user_id": None},
        }
        self.states[entity_id] = state
        return state

    def sensor(self, entity_id: str, value: str, *, device_class: str | None = "occupancy", **registry: Any) -> None:
        self.entities.append(entity(entity_id, **registry))
        self.state(entity_id, value, device_class=device_class)

    async def change(self, entity_id: str, value: str | None, **attributes: Any) -> None:
        """Changes (or removes, with `None`) an entity and notifies the subscribers."""
        old = self.states.get(entity_id)
        new = None
        if value is None:
            self.states.pop(entity_id, None)
        else:
            new = self.state(entity_id, value, **{**(old or {}).get("attributes", {}), **attributes})
        await self.fire(self.state_changed(entity_id, old, new))

    def expose(
        self, entity_id: str, value: str, *, area_id: str | None = None, device_id: str | None = None, **attributes: Any
    ) -> None:
        """An entity in the registry, exposed to Assist, with its state."""
        self.entities.append(entity(entity_id, area_id=area_id, device_id=device_id))
        self.exposed[entity_id] = {"conversation": True}
        self.state(entity_id, value, **attributes)

    async def registry_updated(self, kind: str) -> None:
        """Notifies the subscribers that a registry changed (`entity_registry_updated`…)."""
        await self.fire({"event_type": kind, "data": {"action": "update"}, "origin": "LOCAL"})

    async def fire(self, event: dict[str, Any]) -> None:
        for connection, subscriptions in list(self._subscribers.items()):
            if (subscription := subscriptions.get(event["event_type"])) is None:
                continue
            if self.chatter:
                await connection.send(json.dumps({"type": "future_message", "payload": {}}))
            await connection.send(json.dumps({"id": subscription, "type": "event", "event": event}))

    def state_changed(self, entity_id: str, old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "event_type": "state_changed",
            "data": {"entity_id": entity_id, "old_state": old, "new_state": new},
            "origin": "LOCAL",
            "time_fired": self._clock.isoformat(),
            "context": {"id": "01JCTXEVENT", "parent_id": None, "user_id": None},
        }

    async def drop(self) -> None:
        """Closes every open connection, as a Home Assistant restart does."""
        for connection in list(self._subscribers):
            await connection.close(1012, "restart")

    async def _handle(self, connection: ServerConnection) -> None:
        self.attempts += 1
        if not self.available:
            await connection.close(1013, "starting")
            return
        if self.silent:
            await connection.wait_closed()
            return
        await connection.send(json.dumps({"type": "auth_required", "ha_version": "2026.10.1"}))
        auth = json.loads(await connection.recv())
        if auth != {"type": "auth", "access_token": self.token}:
            await connection.send(json.dumps({"type": "auth_invalid", "message": "Invalid access token or password"}))
            await connection.close()
            return
        await connection.send(json.dumps({"type": "auth_ok", "ha_version": "2026.10.1"}))
        try:
            async for raw in connection:
                await self._command(connection, json.loads(raw))
        except ConnectionClosed:
            pass
        finally:
            self._subscribers.pop(connection, None)

    async def _command(self, connection: ServerConnection, message: dict[str, Any]) -> None:
        kind, message_id = message["type"], message["id"]
        if self.chatter:
            await connection.send(json.dumps({"type": "future_message", "payload": {}}))
        if kind in self.refused or (kind == "subscribe_events" and message["event_type"] in self.refused_events):
            error = {"code": "unauthorized", "message": "Unauthorized"}
            await connection.send(json.dumps({"id": message_id, "type": "result", "success": False, "error": error}))
            return
        result: Any = None
        match kind:
            case "config/floor_registry/list":
                result = self.floors
            case "config/area_registry/list":
                result = self.areas
            case "config/device_registry/list":
                result = self.devices
            case "config/entity_registry/list":
                result = self.entities
            case "homeassistant/expose_entity/list":
                result = {"exposed_entities": self.exposed}
            case "config/entity_registry/get_entries":
                entries = {e["entity_id"]: e for e in self.entities}
                result = {
                    eid: {**entries[eid], "aliases": self.aliases.get(eid, [None]), "device_class": None}
                    if eid in entries
                    else None
                    for eid in message["entity_ids"]
                }
            case "get_states":
                result = list(self.states.values())
                for event in self.before_snapshot:
                    subscription = self._subscribers[connection]["state_changed"]
                    await connection.send(json.dumps({"id": subscription, "type": "event", "event": event}))
            case "subscribe_events":
                self._subscribers.setdefault(connection, {})[message["event_type"]] = message_id
        if kind in self.malformed:
            result = [{"entity_id": 42}]
        await connection.send(json.dumps({"id": message_id, "type": "result", "success": True, "result": result}))


async def settle(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


def people_of(presence: Presence) -> dict[PersonId, Whereabouts]:
    return dict(presence.people)


@pytest.fixture
async def home() -> AsyncIterator[FakeHomeAssistant]:
    async with FakeHomeAssistant() as fake:
        yield fake


@pytest.fixture
async def started() -> AsyncIterator[Callable[..., Any]]:
    """Starts sources (or whole homes) and closes them after the test."""
    sources: list[HomeAssistantPresence | HomeAssistant] = []

    async def start[S: HomeAssistantPresence | HomeAssistant](source: S) -> S:
        sources.append(source)
        await source.start()
        return source

    yield start
    for source in sources:
        await source.close()


ALICE_AND_BOB = PresenceMapping(people={ALICE: "person.alice", BOB: "person.bob"})


class TestHomeAssistantPresence(PresenceSourceContract):
    @pytest.fixture(autouse=True)
    async def _home(self) -> AsyncIterator[None]:
        async with FakeHomeAssistant() as home:
            home.state("person.alice", "home")
            home.state("person.bob", "not_home")
            home.devices.append(device("aqara-1", "kitchen"))
            home.sensor("binary_sensor.kitchen_motion", "on", device_class="motion", device_id="aqara-1")
            home.entities.append(entity("sensor.alice_phone_area", area_id=None))
            home.state("sensor.alice_phone_area", "Salon")
            self._source = home.source(
                PresenceMapping(
                    people={ALICE: "person.alice", BOB: "person.bob"}, rooms={ALICE: "sensor.alice_phone_area"}
                )
            )
            await self._source.start()
            yield
            await self._source.close()

    def source(self) -> HomeAssistantPresence:
        return self._source

    def expected(self) -> Mapping[PersonId, Whereabouts]:
        return {ALICE: Whereabouts(home=True, room="living_room"), BOB: Whereabouts(home=False)}


@pytest.mark.parametrize(
    ("state", "home_value"),
    [("home", True), ("not_home", False), ("Work", False), ("unknown", None), ("unavailable", None)],
)
async def test_a_person_entity_state_reads_as_home_away_or_unknown(
    home: FakeHomeAssistant, started: Any, state: str, home_value: bool | None
) -> None:
    home.state("person.alice", state)
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    assert source.presence().of(ALICE) == Whereabouts(home=home_value)


async def test_a_person_without_an_entity_in_home_assistant_is_unknown(home: FakeHomeAssistant, started: Any) -> None:
    home.state("person.alice", "home")
    source = await started(home.source(ALICE_AND_BOB))
    assert people_of(source.presence()) == {ALICE: Whereabouts(home=True), BOB: Whereabouts()}


async def test_an_installation_without_any_sensor_only_tells_home_or_away(
    home: FakeHomeAssistant, started: Any
) -> None:
    home.state("person.alice", "home")
    home.state("light.kitchen", "on")
    home.sensor("binary_sensor.front_door", "on", device_class="door", area_id="kitchen")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    assert source.granularity is Granularity.HOME
    assert source.presence().occupied_rooms == frozenset()


async def test_occupancy_sensors_mark_their_areas_occupied(home: FakeHomeAssistant, started: Any) -> None:
    home.devices += [device("aqara-1", "kitchen"), device("aqara-2", "office")]
    home.sensor("binary_sensor.kitchen_motion", "on", device_class="motion", device_id="aqara-1")
    home.sensor("binary_sensor.office_presence", "off", device_class="presence", device_id="aqara-2")
    # the entity's own area wins over its device's
    home.sensor("binary_sensor.sofa_occupancy", "on", device_id="aqara-2", area_id="living_room")
    source = await started(home.source(PresenceMapping(people={})))
    assert source.granularity is Granularity.OCCUPIED_ROOMS
    assert source.presence().occupied_rooms == {"kitchen", "living_room"}


async def test_occupancy_sensors_without_an_area_do_not_count(home: FakeHomeAssistant, started: Any) -> None:
    home.devices.append(device("aqara-1", None))
    home.sensor("binary_sensor.hall_motion", "on", device_class="motion", device_id="aqara-1")
    home.sensor("binary_sensor.attic_motion", "on", device_class="motion", area_id="attic")  # deleted area
    home.state("binary_sensor.unregistered_motion", "on", device_class="motion")
    source = await started(home.source(PresenceMapping(people={})))
    assert source.granularity is Granularity.HOME


async def test_configured_occupancy_sensors_replace_discovery(
    home: FakeHomeAssistant, started: Any, caplog: pytest.LogCaptureFixture
) -> None:
    home.sensor("binary_sensor.kitchen_motion", "on", device_class="motion", area_id="kitchen")
    home.sensor("input_boolean.office_busy", "on", device_class=None, area_id="office")
    home.sensor("binary_sensor.hall_motion", "on", device_class="motion")
    mapping = PresenceMapping(people={}, occupancy_sensors=("input_boolean.office_busy", "binary_sensor.hall_motion"))
    source = await started(home.source(mapping))
    assert source.presence().occupied_rooms == {"office"}
    assert "binary_sensor.hall_motion" in caplog.text  # told it has no area


async def test_room_trackers_place_people_in_areas_named_by_id_name_or_alias(
    home: FakeHomeAssistant, started: Any
) -> None:
    home.state("person.alice", "home")
    home.state("person.bob", "home")
    home.state("sensor.alice_room", "kitchen")  # ESPresense: the area id
    home.state("sensor.bob_area", "living room")  # Bermuda: the area name
    mapping = PresenceMapping(people=ALICE_AND_BOB.people, rooms={ALICE: "sensor.alice_room", BOB: "sensor.bob_area"})
    source = await started(home.source(mapping))
    assert source.granularity is Granularity.PERSON_ROOM
    assert people_of(source.presence()) == {
        ALICE: Whereabouts(home=True, room="kitchen"),
        BOB: Whereabouts(home=True, room="living_room"),
    }


async def test_whereabouts_date_from_the_last_change_of_the_person_or_of_their_room(
    home: FakeHomeAssistant, started: Any
) -> None:
    arrived = home.state("person.alice", "home")["last_changed"]
    moved = home.state("sensor.alice_room", "kitchen")["last_changed"]
    left = home.state("person.bob", "not_home")["last_changed"]
    home.state("sensor.bob_area", "kitchen")
    mapping = PresenceMapping(people=ALICE_AND_BOB.people, rooms={ALICE: "sensor.alice_room", BOB: "sensor.bob_area"})
    source = await started(home.source(mapping))
    presence = source.presence()
    assert presence.of(ALICE).since == datetime.fromisoformat(moved) > datetime.fromisoformat(arrived)
    assert presence.of(BOB).since == datetime.fromisoformat(left), "someone away is not dated by a stale tracker"


@pytest.mark.parametrize(("person", "tracker"), [("home", "not_home"), ("home", "Garage"), ("not_home", "Kitchen")])
async def test_a_room_is_only_given_for_someone_home_in_a_known_area(
    home: FakeHomeAssistant, started: Any, person: str, tracker: str
) -> None:
    home.state("person.alice", person)
    home.state("sensor.alice_area", tracker)
    source = await started(
        home.source(PresenceMapping(people={ALICE: "person.alice"}, rooms={ALICE: "sensor.alice_area"}))
    )
    assert source.presence().of(ALICE).room is None


async def test_configured_room_trackers_missing_from_home_assistant_do_not_raise_the_granularity(
    home: FakeHomeAssistant, started: Any
) -> None:
    home.state("person.alice", "home")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"}, rooms={ALICE: "sensor.gone"})))
    assert source.granularity is Granularity.HOME
    assert source.presence().of(ALICE) == Whereabouts(home=True)


async def test_a_state_change_updates_presence_live(home: FakeHomeAssistant, started: Any) -> None:
    home.state("person.alice", "home")
    home.sensor("binary_sensor.kitchen_motion", "off", area_id="kitchen")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    await home.change("person.alice", "not_home")
    await home.change("binary_sensor.kitchen_motion", "on")
    await settle(lambda: source.presence().occupied_rooms == {"kitchen"})
    assert source.presence().of(ALICE) == Whereabouts(home=False)


async def test_a_removed_person_entity_becomes_unknown(home: FakeHomeAssistant, started: Any) -> None:
    home.state("person.alice", "home")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    await home.change("person.alice", None)
    await settle(lambda: source.presence().of(ALICE) == Whereabouts())


async def test_events_fired_while_the_snapshot_is_read_do_not_overwrite_newer_states(
    home: FakeHomeAssistant, started: Any
) -> None:
    stale = home.state("person.alice", "not_home")
    home.state("person.alice", "home")
    home.before_snapshot = [home.state_changed("person.alice", None, stale)]
    source = await started(home.source(ALICE_AND_BOB))
    await home.change("person.bob", "home")  # a later event: the earlier ones have been handled
    await settle(lambda: source.presence().of(BOB) == Whereabouts(home=True))
    assert source.presence().of(ALICE) == Whereabouts(home=True)


async def test_messages_outside_the_protocol_are_ignored(home: FakeHomeAssistant, started: Any) -> None:
    home.chatter = True
    home.state("person.alice", "home")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    await home.change("person.alice", "not_home")
    await settle(lambda: source.presence().of(ALICE) == Whereabouts(home=False))


async def test_a_malformed_event_is_skipped_without_losing_the_connection(
    home: FakeHomeAssistant, started: Any
) -> None:
    home.state("person.alice", "home")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    malformed = {"event_type": "state_changed", "data": {"entity_id": 1}}
    for connection, subscriptions in home._subscribers.items():
        await connection.send(json.dumps({"id": subscriptions["state_changed"], "type": "event", "event": malformed}))
    await home.change("person.alice", "not_home")
    await settle(lambda: source.presence().of(ALICE) == Whereabouts(home=False))
    assert home.attempts == 1


async def test_a_lost_connection_makes_everyone_unknown_until_home_assistant_is_back(
    home: FakeHomeAssistant, started: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    home.state("person.alice", "home")
    home.sensor("binary_sensor.kitchen_motion", "on", area_id="kitchen")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    home.available = False
    await home.drop()
    await settle(lambda: home.attempts >= 3)  # retrying, with a delay
    presence = source.presence()
    assert people_of(presence) == {ALICE: Whereabouts()}
    assert source.health() is Health.UNAVAILABLE and source.brand == "homeassistant"
    assert presence.occupied_rooms == frozenset()
    assert source.granularity is Granularity.OCCUPIED_ROOMS  # what the installation offers, once back
    home.state("person.alice", "not_home")  # changed while Nestor was not listening
    home.available = True
    await settle(lambda: source.presence().of(ALICE) == Whereabouts(home=False))
    assert source.presence().occupied_rooms == {"kitchen"}
    assert source.health() is Health.STARTED
    gone = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and "unavailable" in r.getMessage()]
    assert len(gone) == 1, "said once, not at each of the attempts"
    assert any("back after" in r.getMessage() and r.levelno == logging.INFO for r in caplog.records)


async def test_a_refused_token_fails_start_clearly_without_revealing_it(
    home: FakeHomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    home.token = "another-token"
    source = home.source(PresenceMapping(people={ALICE: "person.alice"}))
    with pytest.raises(ProviderError, match="access token refused") as error:
        await source.start()
    assert error.value.transient is False
    assert TOKEN not in str(error.value)
    ours = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("nestor"))
    assert "> TEXT" in ours  # websockets' frame log is on, and goes through Nestor's logger
    assert TOKEN[:12] not in ours and TOKEN[-12:] not in ours
    await source.close()


async def test_a_token_refused_on_reconnection_stops_the_retries(home: FakeHomeAssistant, started: Any) -> None:
    home.state("person.alice", "home")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    home.token = "rotated"
    await home.drop()
    await settle(lambda: home.attempts == 2)
    await asyncio.sleep(0.2)  # several retry delays
    assert home.attempts == 2
    assert source.presence().of(ALICE) == Whereabouts()


async def test_an_unreachable_home_assistant_does_not_prevent_starting(started: Any) -> None:
    async with FakeHomeAssistant() as gone:
        url = gone.url
    source = await started(HomeAssistantPresence(url, TOKEN, PresenceMapping(people={ALICE: "person.alice"})))
    presence = source.presence()
    assert (presence.granularity, people_of(presence)) == (Granularity.HOME, {ALICE: Whereabouts()})


@pytest.mark.parametrize("failure", ["unavailable", "silent", "refused", "malformed"])
async def test_presence_stays_unknown_until_home_assistant_answers_properly(
    home: FakeHomeAssistant, started: Any, failure: str
) -> None:
    home.state("person.alice", "home")
    match failure:
        case "unavailable":
            home.available = False
        case "silent":
            home.silent = True
        case "refused":
            home.refused.add("config/entity_registry/list")
        case "malformed":
            home.malformed.add("get_states")
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"}), sync_timeout_s=0.1))
    await settle(lambda: home.attempts >= 2)
    assert source.presence().of(ALICE) == Whereabouts()
    home.available, home.silent = True, False
    home.refused.clear()
    home.malformed.clear()
    await settle(lambda: source.presence().of(ALICE) == Whereabouts(home=True))


@pytest.mark.parametrize(
    "replies",
    [
        ['{"hello": "world"}'],
        ["[1, 2]"],
        ["<html>Bad gateway</html>"],
        ['{"type": "auth_required"}', '{"type": "result", "success": true}'],
    ],
)
async def test_a_server_that_is_not_home_assistant_is_treated_as_unavailable(started: Any, replies: list[str]) -> None:
    async def impostor(connection: ServerConnection) -> None:
        await connection.send(replies[0])
        for reply in replies[1:]:
            await connection.recv()
            await connection.send(reply)
        await connection.wait_closed()

    async with serve(impostor, "127.0.0.1", 0) as server:
        host, port = next(iter(server.sockets)).getsockname()[:2]
        mapping = PresenceMapping(people={ALICE: "person.alice"})
        source = await started(HomeAssistantPresence(f"http://{host}:{port}", TOKEN, mapping, reconnect_min_s=10))
        assert source.presence().of(ALICE) == Whereabouts()


async def test_close_is_idempotent_and_leaves_presence_unknown(home: FakeHomeAssistant) -> None:
    home.state("person.alice", "home")
    source = home.source(PresenceMapping(people={ALICE: "person.alice"}))
    await source.start()
    await source.start()  # already started: no second connection
    await source.close()
    await source.close()
    assert home.attempts == 1
    assert source.presence().of(ALICE) == Whereabouts()


async def test_the_plugin_builds_the_home_its_presence_and_its_overview_from_one_configuration(
    home: FakeHomeAssistant, started: Any, tmp_path: Path
) -> None:
    home.state("person.alice", "home")
    home.state("person.bob", "not_home", friendly_name="Bob Martin")
    home.state("sensor.alice_area", "Office")
    home.sensor("binary_sensor.kitchen_motion", "on", area_id="kitchen")
    home.sensor("binary_sensor.office_motion", "on", area_id="office")
    raw = {
        "url": home.url + "/",
        "token": TOKEN,
        "people": {"alice": "person.alice"},
        "rooms": {"alice": "sensor.alice_area"},
        "occupancy_sensors": ["binary_sensor.kitchen_motion", "binary_sensor.hall_motion"],
    }
    built = plugin.create(raw, "home", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR")))
    assert isinstance(built, HomeAssistant) and built.name == "home"
    await started(built)
    presence = built.presence.presence()
    assert presence.granularity is Granularity.PERSON_ROOM
    assert people_of(presence) == {ALICE: Whereabouts(home=True, room="office")}
    assert presence.occupied_rooms == {"kitchen"}
    overview = built.overview()
    assert overview.connected and overview.people == {ALICE: "person.alice"}
    assert overview.trackers == {ALICE: "sensor.alice_area"}
    assert overview.rooms == (
        Room("living_room", "Living Room", aliases=("Salon",)),
        Room("kitchen", "Kitchen", occupied=True),
        Room("office", "Office"),
    ), "occupied only where a sensor tells"
    assert overview.residents == (
        Resident("person.alice", "Alice", home=True),
        Resident("person.bob", "Bob Martin", home=False),
    )
    assert overview.unplaced_sensors == ("binary_sensor.hall_motion",)
    assert built.health() is Health.DEGRADED, "its MCP server does not answer here: presence alone"
    assert built.tools is not None and (await built.tools.endpoint())[0] == f"{home.url}/api/mcp", "its own, by default"


async def test_the_home_shows_what_home_assistant_exposes_to_assist_by_room_and_device_and_follows_its_changes(
    home: FakeHomeAssistant, started: Any, tmp_path: Path
) -> None:
    """As Assist's own static context: what is exposed only, by its name and aliases, in its room or its device's, the
    entities of one device in one room as one device; without a state; sensitive only for what acts. A registry change
    (an entity exposed) is followed live."""
    home.floors = [{"floor_id": "ground", "name": "Ground floor", "aliases": [], "level": 0, "icon": None}]
    home.areas[1]["floor_id"] = "ground"
    home.devices = [
        device("washer", "kitchen", "Washing Machine"),
        device("tv", "living_room", "TV"),
        device("relay", "kitchen", "Dual relay"),
    ]
    home.expose("sensor.washing_machine_phase", "rinse", device_id="washer", friendly_name="Washing Machine Phase")
    home.expose(
        "binary_sensor.washing_machine_door_lock", "on", device_id="washer", friendly_name="Washing Machine Door lock"
    )
    home.expose("switch.washing_machine", "off", device_id="washer", friendly_name="Washing Machine")
    home.expose("media_player.tv", "off", device_id="tv", friendly_name="TV", device_class="tv")
    home.expose("light.kitchen", "on", area_id="kitchen", friendly_name="Kitchen light")
    home.expose("lock.front_door", "locked", friendly_name="Front door")
    home.expose("light.relay_1", "off", device_id="relay", friendly_name="Pantry")
    home.expose("light.relay_2", "off", device_id="relay", area_id="living_room", friendly_name="Garage door")
    home.aliases["media_player.tv"] = [None, "Télé"]
    home.sensor("sensor.washing_machine_energy", "2.1", device_class="energy", device_id="washer")  # not exposed
    raw = {"url": home.url, "token": TOKEN}
    built = plugin.create(raw, "home", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR")))
    assert isinstance(built, HomeAssistant)
    await started(built)

    overview = built.overview()
    rooms = {room.id: room for room in overview.rooms}
    assert rooms["kitchen"].floor == "Ground floor" and rooms["living_room"].floor is None
    assert rooms["kitchen"].devices == (
        Device(id="light.kitchen", name="Kitchen light", kinds=("light",)),
        Device(id="light.relay_1", name="Pantry", kinds=("light",)),
        Device(
            id="sensor.washing_machine_phase",
            name="Washing Machine",
            kinds=("sensor", "binary_sensor", "switch"),
            parts=("Door lock", "Phase"),  # a door-lock sensor only reports: nothing in it to confirm
        ),
    )
    assert rooms["living_room"].devices == (
        Device(id="light.relay_2", name="Garage door", kinds=("light",), sensitive=True),  # its relay, set elsewhere
        Device(id="media_player.tv", name="TV", kinds=("media_player",), aliases=("Télé",)),
    )
    assert overview.devices == (Device(id="lock.front_door", name="Front door", kinds=("lock",), sensitive=True),), (
        "in no room"
    )

    home.expose("light.office", "off", area_id="office", friendly_name="Desk lamp")
    await home.registry_updated("entity_registry_updated")  # then its first state, as Home Assistant does
    await home.change("light.office", "off", friendly_name="Desk lamp")
    lamp = (Device(id="light.office", name="Desk lamp", kinds=("light",)),)
    await settle(lambda: any(r.id == "office" and r.devices == lamp for r in built.overview().rooms))
    assert home.attempts == 1, "followed on the same connection"

    home.available = False  # Home Assistant restarts: the house stays as last known, nobody placed in it
    await home.drop()
    await settle(lambda: not built.overview().connected)
    gone = built.overview()
    assert [r.devices for r in gone.rooms] == [r.devices for r in built.overview().rooms] and gone.devices
    assert next(r for r in gone.rooms if r.id == "office").devices == lamp


async def test_a_home_assistant_that_will_not_say_what_it_exposes_keeps_its_presence_without_a_map(
    home: FakeHomeAssistant, started: Any
) -> None:
    """An older version (no floors) or a token without the right to read what is exposed or to follow the registries:
    presence goes on."""
    home.state("person.alice", "home")
    home.expose("light.kitchen", "on", area_id="kitchen", friendly_name="Kitchen light")
    home.refused |= {"config/floor_registry/list", "homeassistant/expose_entity/list"}
    home.refused_events |= {"floor_registry_updated", "entity_registry_updated"}
    source = await started(home.source(PresenceMapping(people={ALICE: "person.alice"})))
    assert source.presence().of(ALICE) == Whereabouts(home=True)
    overview = source.overview()
    assert overview.connected and all(not r.devices and r.floor is None for r in overview.rooms)
    assert home.attempts == 1


async def test_a_home_assistant_that_does_not_answer_leaves_the_home_unavailable_and_says_how_it_is_tied(
    started: Any, tmp_path: Path
) -> None:
    async with FakeHomeAssistant() as gone:
        url = gone.url
    raw = {"url": url, "token": TOKEN, "people": {"alice": "person.alice"}, "reconnect_min_s": 30}
    built = plugin.create(raw, "home", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR")))
    assert isinstance(built, HomeAssistant)
    await started(built)
    overview = built.overview()
    assert (overview.connected, overview.rooms, overview.people) == (False, (), {ALICE: "person.alice"})
    assert built.health() is Health.UNAVAILABLE and built.tools.tools() == ()


@pytest.mark.parametrize(
    ("arguments", "sensitive"),
    [
        ({"name": "Salon", "domain": ["light"]}, False),
        ({"name": "Front door", "domain": ["lock"]}, True),
        ({"name": "Portail", "device_class": ["gate"]}, True),
        ({"name": "Garage door"}, True),
    ],
)
def test_by_default_locks_the_alarm_and_doors_need_a_go_ahead_whatever_the_tool_not_lights(
    arguments: dict[str, Any], sensitive: bool
) -> None:
    rule = HomeAssistantSettings(url="http://ha.local:8123", token=TOKEN).sensitive.calls().rule()
    assert rule.applies_to("intent__HassTurnOff", Risk.WRITE) and rule.applies_to("light__HassLightSet", Risk.WRITE)
    assert not rule.applies_to("homeassistant__GetLiveContext", Risk.READ), "a rule never makes a read sensitive"
    assert rule.matches(arguments) is sensitive


def test_a_reverse_proxy_prefix_is_kept_in_the_websocket_url() -> None:
    assert websocket_url("https://example.org/ha/") == "wss://example.org/ha/api/websocket"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"url": "ftp://ha.example"}, "http"),
        ({"url": "homeassistant.local:8123"}, "http"),
        ({"rooms": {"bob": "sensor.bob_area"}}, "without a person entity: bob"),
        ({"reconnect_min_s": 10, "reconnect_max_s": 5}, "reconnect_max_s"),
        ({"mcp": {"token": "t"}}, r"^[^;]*mcp\.url: Field required$"),  # said at its field, once
        ({"tool_timeout_s": 5, "mcp": {"url": "https://mcp.example/mcp"}}, "set mcp.timeout_s instead"),
    ],
)
def test_the_plugin_rejects_an_inconsistent_configuration(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    raw = {"url": "http://ha.local:8123", "token": TOKEN, "people": {"alice": "person.alice"}, **change}
    with pytest.raises(ContractError, match=message):
        plugin.create(raw, "home", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR")))


# -- the server of its actions ---------------------------------------------------------------------------------

OTHER_TOKEN = "another-servers-token"


def actions_server() -> MCPServer:
    """Another MCP server for the home's actions, with its own catalogue."""
    server = MCPServer("another-home")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def home_state() -> str:
        return "front door: locked"

    @server.tool()
    def set_device(name: str, domain: str) -> str:
        return f"{name} set"

    @server.tool()
    def reboot() -> str:
        return "rebooting"

    return server


@pytest.fixture
async def other_server() -> AsyncIterator[Served]:
    served = Served(lambda: bearer(actions_server().streamable_http_app(), OTHER_TOKEN))
    await served.start()
    yield served
    await served.stop()


def home_with(home: FakeHomeAssistant, tmp_path: Path, mcp: object) -> HomeAssistant:
    raw = {"url": home.url, "token": TOKEN, "people": {"alice": "person.alice"}, "mcp": mcp}
    built = plugin.create(raw, "home", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR")))
    assert isinstance(built, HomeAssistant)
    return built


async def test_another_actions_server_alone_serves_the_home_with_its_settings_and_the_homes_sensitive_targets(
    home: FakeHomeAssistant, other_server: Served, started: Any, tmp_path: Path
) -> None:
    home.state("person.alice", "home")
    mcp = {"url": other_server.url(), "token": OTHER_TOKEN, "exclude": ["reboot"], "risks": {"home_state": "write"}}
    built = await started(home_with(home, tmp_path, mcp))
    assert built.tools is not None
    assert {t.name: t.risk for t in built.tools.tools()} == {"home_state": Risk.WRITE, "set_device": Risk.WRITE}
    assert built.health() is Health.STARTED, "Home Assistant's own server is never asked"
    set_device = next(t for t in built.tools.tools() if t.name == "set_device")
    assert set_device.risk_of({"name": "Salon", "domain": "light"}) is Risk.WRITE
    assert set_device.risk_of({"name": "Entrée", "domain": "lock"}) is Risk.SENSITIVE, "the home's rule still holds"
    assert people_of(built.presence.presence()) == {ALICE: Whereabouts(home=True)}


async def test_a_home_without_actions_tells_presence_only_and_offers_no_tools(
    home: FakeHomeAssistant, started: Any, tmp_path: Path
) -> None:
    home.state("person.alice", "home")
    built = await started(home_with(home, tmp_path, False))
    assert built.tools is None
    assert built.health() is Health.STARTED and built.health_detail() is None, "no server it does not use"
    assert "tools" not in built.details()
    assert people_of(built.presence.presence()) == {ALICE: Whereabouts(home=True)}

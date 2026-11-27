"""What the agent knows of the home without asking it: its rooms and what its system shows in each, with Nestor's own
satellites, in the household layer (it changes when the home does, so a provider's prompt cache keeps it); who is home
now, in the turn's, for someone of the household only. No state of a device: the home's tools read it when it matters,
as Home Assistant's Assist does."""

from collections.abc import Callable, Iterable

from nestor.modules.conversation import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.home.ports import Home
from nestor.modules.home.types import Device, Granularity, HomeOverview, Room
from nestor.modules.household import Household

MAP = (
    "The home, as its system shows it to you. Names are its own: give them to its tools. What exists and where, answer "
    "from here. States are not here: read them with its tools only when the question is about them."
)
CUT = "(more devices than fit here: the home's tools list them)"
LIMIT = 8000  # characters: past it, the parts go, then the devices that do not fit

type Satellites = Callable[[], Iterable[tuple[str, str]]]  # each satellite: the room it is in, as named, and its name


class HomeContext(ContextProvider):
    """The home's map and who is home. `satellites`: Nestor's own devices and where they are; `limit`: the most the
    map may take, in characters."""

    def __init__(
        self, home: Home, household: Household, satellites: Satellites = lambda: (), *, limit: int = LIMIT
    ) -> None:
        self.home, self.household, self.satellites, self.limit = home, household, satellites, limit

    async def context(self, turn: TurnContext) -> Sections:
        overview = self.home.overview()
        if not overview.rooms and not overview.devices:
            return {}  # never connected: nothing known of the house
        sections = {Layer.HOUSEHOLD: self._map(overview)}  # the last known while it reconnects: the house is the same
        if overview.connected and turn.speaker.private and (who := self._who(overview)):
            sections[Layer.TURN] = who
        return sections

    def _map(self, overview: HomeOverview) -> str:
        satellites: dict[str, list[str]] = {}
        for room, name in self.satellites():
            if (found := self.home.room_of(room)) is not None:
                satellites.setdefault(found, []).append(name)
        full = _render(overview, satellites, parts=True)
        if len(full) <= self.limit:
            return full
        brief = _render(overview, satellites, parts=False)
        if len(brief) <= self.limit:
            return brief
        kept = brief[: self.limit - len(CUT) - 1].rsplit("\n", 1)[0]  # whole lines only, the note within the limit
        return f"{kept}\n{CUT}"

    def _who(self, overview: HomeOverview) -> str | None:
        presence = self.home.presence.presence()
        lines = [f"- {self.household.name_of(p, p)}: {said}" for p, said in presence.told(overview.rooms).items()]
        if presence.granularity is Granularity.OCCUPIED_ROOMS:
            names = [r.name for r in overview.rooms if r.id in presence.occupied_rooms]
            lines.append(f"Occupied rooms: {', '.join(names) or 'none'}")
        return "Who is home now:\n" + "\n".join(lines) if lines else None


def _render(overview: HomeOverview, satellites: dict[str, list[str]], *, parts: bool) -> str:
    lines = [MAP]
    floors = list(dict.fromkeys(room.floor for room in overview.rooms))
    for floor in floors:
        rooms = [room for room in overview.rooms if room.floor == floor]
        if floors != [None]:
            lines.append(f"{floor or 'On no floor'}:")
        lines += [_room(room, satellites.get(room.id, ()), parts=parts) for room in rooms]
    if overview.devices:
        lines.append(f"- No room: {_devices(overview.devices, parts=parts)}")
    return "\n".join(lines)


def _room(room: Room, satellites: Iterable[str], *, parts: bool) -> str:
    aliases = f" (also {', '.join(room.aliases)})" if room.aliases else ""
    things = [_devices(room.devices, parts=parts)] if room.devices else []
    things += [f"Nestor's satellite {name}" for name in satellites]
    return f"- {room.name}{aliases}: {'; '.join(things) or 'nothing shown'}"


def _devices(devices: Iterable[Device], *, parts: bool) -> str:
    return "; ".join(_device(device, parts=parts) for device in devices)


def _device(device: Device, *, parts: bool) -> str:
    traits = [*device.kinds, *(["sensitive"] if device.sensitive else [])]
    aliases = f", also {', '.join(device.aliases)}" if device.aliases else ""
    shown = f": {', '.join(device.parts)}" if parts and device.parts else ""
    return f"{device.name} ({', '.join(traits)}{aliases}){shown}"

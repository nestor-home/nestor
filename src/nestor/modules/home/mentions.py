"""The home's rooms and devices, named with `@` in a message: `@salon` says where, `@tv-lg-c6` what."""

from collections.abc import Iterable

from nestor.modules.conversation import Mentioned, MentionKind, MentionSource
from nestor.modules.home.ports import Home
from nestor.modules.household import Person


class HomeMentions(MentionSource):
    """Every room the home system knows and every device it shows its assistant, for anyone: what it has right now,
    nothing when it does not answer. A device is known by its name; its room, when it has one, is said with it."""

    def __init__(self, home: Home) -> None:
        self.home = home

    def mentionable(self, person: Person | None) -> Iterable[Mentioned]:
        overview = self.home.overview()
        for room in overview.rooms:
            yield Mentioned(
                kind=MentionKind.ROOM, id=room.id, handle=room.id, label=room.name, aliases=(room.name, *room.aliases)
            )
        placed = [(device, room.name) for room in overview.rooms for device in room.devices]
        for device, room in [*placed, *((device, None) for device in overview.devices)]:
            yield Mentioned(
                kind=MentionKind.DEVICE,
                id=f"{room}/{device.name}" if room else device.name,
                handle=device.name,
                label=device.name,
                aliases=(device.name, *device.aliases),
            )

    def instruction(self, mentioned: Mentioned) -> str:
        if mentioned.kind is MentionKind.DEVICE:
            room, _, _ = mentioned.id.rpartition("/")
            where = f" in {room}" if room else ""
            return f"the device {mentioned.label}{where} of the home: what the message asks is about it"
        return f"the room {mentioned.label} (area {mentioned.id}) of the home: what the message asks happens there"

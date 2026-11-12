"""The home's rooms, named with `@` in a message: `@salon` says where."""

from collections.abc import Iterable

from nestor.modules.conversation import Mentioned, MentionKind, MentionSource
from nestor.modules.home.ports import Home
from nestor.modules.household import Person


class RoomMentions(MentionSource):
    """Every room the home system knows, for anyone: what it has right now, nothing when it does not answer."""

    def __init__(self, home: Home) -> None:
        self.home = home

    def mentionable(self, person: Person | None) -> Iterable[Mentioned]:
        for room in self.home.overview().rooms:
            yield Mentioned(kind=MentionKind.ROOM, id=room.id, handle=room.id, label=room.name, aliases=(room.name,))

    def instruction(self, mentioned: Mentioned) -> str:
        return f"the room {mentioned.label} (area {mentioned.id}) of the home: what the message asks happens there"

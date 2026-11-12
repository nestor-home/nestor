"""Home: the home system the household lives with, plugged once (Home Assistant…).

Nestor never infers presence on its own: the home relays what it already knows, at the finest level it offers
(home or away; occupied rooms; who is in which room). It also offers the agent its actions (lights, heating, media,
locks) as tools, the household deciding which need a person's go-ahead, and shows its rooms and residents.
"""

from nestor.modules.home.events import PresenceChanged
from nestor.modules.home.mentions import RoomMentions
from nestor.modules.home.ports import Home, PresenceSource
from nestor.modules.home.types import Granularity, HomeOverview, Presence, Resident, Room, Whereabouts

__all__ = [
    "Granularity",
    "Home",
    "HomeOverview",
    "Presence",
    "PresenceChanged",
    "PresenceSource",
    "Resident",
    "Room",
    "RoomMentions",
    "Whereabouts",
]

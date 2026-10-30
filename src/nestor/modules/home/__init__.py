"""Home: who is home and where, as the home automation system knows it.

Nestor never infers presence on its own: a `PresenceSource` relays what the home already knows, at
the finest level it offers (home or away; occupied rooms; who is in which room). Controlling
devices goes through the home system's own agent tools (Home Assistant's MCP server), not here.
"""

from nestor.modules.home.events import PresenceChanged
from nestor.modules.home.ports import PresenceSource
from nestor.modules.home.types import Granularity, Presence, Whereabouts

__all__ = ["Granularity", "Presence", "PresenceChanged", "PresenceSource", "Whereabouts"]

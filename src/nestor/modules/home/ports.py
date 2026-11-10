"""The home ports: the home system Nestor lives with, and the presence it relays."""

from abc import ABC, abstractmethod

from nestor.core import Component
from nestor.modules.cognition.tools import ToolProvider
from nestor.modules.home.types import Granularity, HomeOverview, Presence


class PresenceSource(Component, ABC):
    """Relays the home system's presence information.

    Contract (checked by `nestor.testing.home.PresenceSourceContract`):
    - `granularity` is what this installation really provides, not what the adapter could provide;
    - `presence()` is cheap (served from a live cache) and never raises: when the home system is
      unreachable it returns everyone as unknown rather than a stale answer presented as fresh;
    - people are household person ids (the adapter maps them from its own entities).
    """

    @property
    @abstractmethod
    def granularity(self) -> Granularity: ...

    @abstractmethod
    def presence(self) -> Presence: ...


class Home(Component, ABC):
    """The home system the household lives with (Home Assistant…), plugged once: who is home and where, the actions
    it offers the agent, and what it can show of itself.

    Contract:
    - `presence` and `tools` are its own: it starts and closes them with itself;
    - `overview()` is cheap (the live view) and never raises: disconnected, it says so and keeps its configuration;
    - a home system that does not answer at start leaves the home unavailable, never stops Nestor; refused
      credentials raise `ProviderError`, not transient.
    """

    @property
    @abstractmethod
    def presence(self) -> PresenceSource: ...

    @property
    @abstractmethod
    def tools(self) -> ToolProvider: ...

    @abstractmethod
    def overview(self) -> HomeOverview: ...

    @abstractmethod
    def room_of(self, label: str) -> str | None:
        """The room a household's word names (a satellite's room: an area's id, name or alias), `None` when the
        home does not know it or does not answer."""

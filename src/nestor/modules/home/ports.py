"""The presence port."""

from abc import ABC, abstractmethod

from nestor.core import Component
from nestor.modules.home.types import Granularity, Presence


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

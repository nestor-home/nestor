"""Capabilities: what a component can do, declared rather than assumed.

A feature asks for a capability, never for a device. Names are dotted strings
(`expression.emotion`, `vision.capture`) so that plugins can declare new ones; the
modules that consume a capability define its constant.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import NewType

from nestor.core.exceptions import CapabilityMissing

Capability = NewType("Capability", str)


@dataclass(frozen=True, slots=True)
class Capabilities:
    items: frozenset[Capability] = frozenset()

    @classmethod
    def of(cls, *capabilities: Capability) -> "Capabilities":
        return cls(frozenset(capabilities))

    @classmethod
    def union(cls, sets: Iterable["Capabilities"]) -> "Capabilities":
        return cls(frozenset().union(*(s.items for s in sets)))

    def __contains__(self, capability: object) -> bool:
        return capability in self.items

    def require(self, capability: Capability) -> None:
        """Fail clearly when a mandatory capability is absent (optional ones are checked with `in`)."""
        if capability not in self.items:
            raise CapabilityMissing(capability, frozenset(self.items))

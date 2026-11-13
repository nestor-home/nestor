"""The inbound port: things arriving from outside that watches may care about."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from types import MappingProxyType

from nestor.core import Component
from nestor.modules.initiative.watches.types import Incoming


class InboundEventSource(Component, ABC):
    """A feed of incoming items (new mails of a mailbox, home events…).

    Contract (checked by `nestor.testing.initiative.InboundEventSourceContract`):
    - `items()` yields each item once while running, in arrival order, until the source is closed;
    - after a restart it resumes where it stopped: nothing arrived meanwhile is lost, nothing
      already taken comes again (the source keeps its own cursor, e.g. a mailbox history id); an item is taken
      at the latest when the next one is asked for, so the last one handed out before a stop may come again
      (its handling may have been cut short), never an earlier one; a source items are pushed to (a webhook)
      receives only while running, and keeps what it accepted until taken;
    - a provider outage pauses the feed and is retried; it never ends `items()` with a vendor error.
    """

    kinds: tuple[str, ...] = ()  # what this source brings ("mail"…): watches can only watch these
    # what it follows by name, for each kind ({"feed": ("LWN",)}): told to the agent, so that a person can name it
    follows: Mapping[str, tuple[str, ...]] = MappingProxyType({})

    @abstractmethod
    def items(self) -> AsyncGenerator[Incoming]: ...

"""The inbound port: things arriving from outside that watches may care about."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from nestor.core import Component
from nestor.modules.initiative.watches.types import Incoming


class InboundEventSource(Component, ABC):
    """A feed of incoming items (new mails of a mailbox, home events…).

    Contract (checked by `nestor.testing.initiative.InboundEventSourceContract`):
    - `items()` yields each item once while running, in arrival order, until the source is closed;
    - after a restart it resumes where it stopped: nothing arrived meanwhile is lost, nothing
      already yielded comes again (the source keeps its own cursor, e.g. a mailbox history id);
    - a provider outage pauses the feed and is retried; it never ends `items()` with a vendor error.
    """

    kinds: tuple[str, ...] = ()  # what this source brings ("mail"…): watches can only watch these

    @abstractmethod
    def items(self) -> AsyncGenerator[Incoming]: ...

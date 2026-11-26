"""The inbound port: things arriving from outside that alerts may wait for."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from types import MappingProxyType

from nestor.core import Component
from nestor.modules.initiative.alerts.types import Incoming


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

    kinds: tuple[str, ...] = ()  # what this source brings ("mail"…): alerts can only wait for these
    # its items say exactly what happened (a webhook's event): an alert on their kind without a condition rings as
    # each arrives, without the triage model; a mail, a feed's entry or a page has to be read first
    structured: bool = False
    # what it follows by name, for each kind ({"feed": ("LWN",)}): told to the agent, so that a person can name it
    follows: Mapping[str, tuple[str, ...]] = MappingProxyType({})

    @abstractmethod
    def items(self) -> AsyncGenerator[Incoming]: ...

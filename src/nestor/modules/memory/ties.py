"""What a memory may be tied to, and how it is untied: a memory that only holds while something runs, a task for
one ("Léa wants to know when the TV drops below 1 000 €"), is retired, with its reason journaled, when that one ends.

Each kind of thing is plugged in as a `Tie`: its name (`task`), the event that ends one, how that event names it,
and whether one is still going on. A memory names what it is tied to as `<kind>:<id>` (`task:3f2a`).
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from nestor.core import Component, ContractError, Event
from nestor.modules.journal import Journal, Subscription
from nestor.modules.memory.service import Memories

log = logging.getLogger("nestor.memory")


@dataclass(frozen=True, slots=True)
class Tie[E: Event]:
    kind: str  # `task`
    ends: type[E]  # the event that ends one
    names: Callable[[E], str]  # the id of the one it ends
    running: Callable[[str], bool]  # whether one, by id, exists and is still going on

    def of(self, ident: str) -> str:
        return f"{self.kind}:{ident}"


class Ties(Component):
    """Retires the memories tied to what ends, as the journal tells it, while Nestor runs."""

    name = "memory-ties"

    def __init__(self, journal: Journal, memories: Memories, ties: Sequence[Tie]) -> None:
        self.journal, self.memories = journal, memories
        self.ties = {t.kind: t for t in ties}
        self._worker: asyncio.Task[None] | None = None
        self._subscription: Subscription | None = None

    @property
    def kinds(self) -> list[str]:
        return list(self.ties)

    def check(self, tie: str) -> str:
        """`tie` as it is kept, when it names something of a known kind that is still going on."""
        kind, _, ident = tie.strip().partition(":")
        known = self.ties.get(kind.strip())
        if known is None or not ident.strip():
            raise ContractError(f"cannot tie a memory to {tie!r}: write {' or '.join(f'{k}:<id>' for k in self.ties)}")
        if not known.running(ident.strip()):
            raise ContractError(f"no {kind} {ident.strip()!r} going on")
        return known.of(ident.strip())

    async def start(self) -> None:
        if not self.ties:
            return
        self._subscription = subscription = self.journal.subscribe(*(t.ends for t in self.ties.values()))
        await self.reconcile()
        self._worker = asyncio.create_task(self._run(subscription), name=self.name)

    async def reconcile(self) -> int:
        """Retire what is tied to something no longer going on: it ended while Nestor was stopped, or its retirement
        failed; how many were."""
        retired = 0
        for tie in {m.tied_to for m in await self.memories.store.everything() if m.tied_to}:
            kind, _, ident = tie.partition(":")
            known = self.ties.get(kind)
            if known is not None and not known.running(ident):
                retired += len(await self.memories.untie(tie))
        return retired

    async def close(self) -> None:
        if self._subscription is not None:
            self._subscription.close()
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def ended(self, event: Event) -> int:
        """Retire what `event` unties; how many were."""
        retired = 0
        for tie in self.ties.values():
            if isinstance(event, tie.ends):
                retired += len(await self.memories.untie(tie.of(tie.names(event))))
        return retired

    async def _run(self, subscription: Subscription) -> None:
        async for event in subscription:
            try:
                await self.ended(event)
            except Exception:  # one failure never stops the next ending from untying; the next start retries it
                log.exception("memories tied to what %s ended were not retired", event.event_type)

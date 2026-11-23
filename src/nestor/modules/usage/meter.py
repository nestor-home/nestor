"""The meter: each call to a model or an executor becomes a `usage.recorded` in the journal, priced and attributed.

A call is counted by whoever makes it on Nestor's behalf (`Metered` around a model, an executor at a task's end),
through `measure`; the record is written in the background, so that a call never waits for it nor fails with it.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date

from nestor.core import Component, Tally, Usage, utc_now
from nestor.modules.journal import Journal
from nestor.modules.usage.attribution import attribution
from nestor.modules.usage.events import UsageRecorded
from nestor.modules.usage.prices import PriceBook
from nestor.modules.usage.types import Attribution, CallPurpose, Consumer, CostBasis, Outcome

log = logging.getLogger("nestor.usage")
SOURCE = "usage"


class Call:
    """A call being measured: what it reports is gathered in `tally`, and how it ended in `outcome`."""

    def __init__(self, consumer: Consumer, said: Attribution) -> None:
        self.consumer, self.said = consumer, said
        self.tally = Tally()
        self.outcome = Outcome.OK
        self.started = time.monotonic()


class Meter(Component):
    name = "meter"

    def __init__(self, journal: Journal, prices: PriceBook) -> None:
        self.journal, self.prices = journal, prices
        self._queue: asyncio.Queue[UsageRecorded | None] = asyncio.Queue()
        self._writer: asyncio.Task[None] | None = None
        self._warned: set[tuple[str, str, date]] = set()  # (consumer, fault, day): warned once a day

    async def start(self) -> None:
        self._writer = asyncio.create_task(self._write(), name="meter")

    async def close(self) -> None:
        """Once every call recorded so far is written."""
        if self._writer is not None:
            self._queue.put_nowait(None)
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer
            self._writer = None

    @contextmanager
    def measure(self, consumer: Consumer, said: Attribution | None = None) -> Generator[Call]:
        """Measure a call made within the block, on behalf of `said`, by default the work in progress; what is
        reported into its `tally` (`counting`, `counted`) is its usage. A cancellation makes it `cancelled`, any
        other error `failed`; either way it is recorded, and the error raised again."""
        call = Call(consumer, said or attribution())
        try:
            yield call
        except (asyncio.CancelledError, GeneratorExit):
            call.outcome = Outcome.CANCELLED
            raise
        except Exception:
            call.outcome = Outcome.FAILED
            raise
        finally:
            self.record(call)

    def record(self, call: Call) -> None:
        """Price and attribute a finished call, then have it written."""
        consumer, usage, said = call.consumer, call.tally.usage, call.said
        priced = self.prices.price(consumer, usage)
        if priced.basis is CostBasis.UNKNOWN and (usage.units or call.outcome is Outcome.OK):
            self._warn(consumer, "unpriced", "%s: no cost said and no price known for %s", usage.served)
        if said.purpose is CallPurpose.UNATTRIBUTED:
            self._warn(consumer, "unattributed", "%s: called with no reason said (%s)", consumer.kind)
        event = UsageRecorded(
            source=SOURCE,
            session=said.session,
            consumer=consumer.key,
            kind=consumer.kind,
            provider=consumer.provider,
            served=usage.served or consumer.model,
            units={u.value: q for u, q in usage.units.items()},
            cost_nusd=priced.cost.nusd if priced.cost else (0 if priced.basis is CostBasis.FREE else None),
            basis=priced.basis,
            price=priced.source,
            duration_ms=round((time.monotonic() - call.started) * 1000),
            outcome=call.outcome,
            purpose=said.purpose,
            person=said.person,
            channel=said.channel,
            medium=said.medium,
            conversation=said.conversation,
            turn=said.turn,
            origin=said.origin,
        )
        self._queue.put_nowait(event)

    def report(self, consumer: Consumer, usage: Usage, *, outcome: Outcome = Outcome.OK) -> None:
        """Record what a consumer says it used after the fact (an executor at a task's end), on behalf of the work in
        progress."""
        call = Call(consumer, attribution())
        call.tally.add(usage)
        call.outcome = outcome
        self.record(call)

    async def _write(self) -> None:
        while (event := await self._queue.get()) is not None:
            try:
                await self.journal.publish(event)
            except Exception:  # a record lost is logged; the meter keeps counting the next calls
                log.exception("could not record the usage of %s", event.consumer)

    def _warn(self, consumer: Consumer, fault: str, message: str, detail: object) -> None:
        key = (consumer.key, fault, utc_now().date())
        if key not in self._warned:
            self._warned.add(key)
            log.warning(message, consumer.key, detail)

"""What a call to a model or an executor consumed, in one vocabulary whatever its type, and the one way to say it.

An adapter measures and says it with `report`, from inside the call: tokens read and written, pictures drawn, seconds
heard, characters spoken, and what the provider billed when it says. It knows neither the price nor on whose behalf
it works: whoever opened the call (`Tally`, `counting`) gathers the reports, and the usage module prices and
attributes them. A call that says nothing consumed nothing anyone knows of.

    report(Usage({Unit.INPUT_TOKENS: 812, Unit.OUTPUT_TOKENS: 64}, cost=Money.usd("0.000412"), served="haiku-4.5"))
"""

from collections.abc import AsyncGenerator, Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

NANO = 10**9  # nano-dollars in a dollar


class Unit(StrEnum):
    """What a call consumes and a price is set by. A new one is added here and nowhere else."""

    INPUT_TOKENS = "input_tokens"  # every token the model read, those read from or written to its cache included
    CACHED_INPUT_TOKENS = "cached_input_tokens"  # of the input, read from the provider's prompt cache
    CACHE_WRITE_TOKENS = "cache_write_tokens"  # of the input, written to the provider's prompt cache
    OUTPUT_TOKENS = "output_tokens"  # every token written, reasoning included
    IMAGES = "images"  # pictures drawn
    AUDIO_SECONDS = "audio_seconds"  # speech heard
    CHARACTERS = "characters"  # text spoken
    REQUESTS = "requests"  # calls billed one by one


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """An amount in US dollars, in whole nano-dollars: never a float, so that sums of small calls stay exact."""

    nusd: int

    @classmethod
    def usd(cls, amount: Decimal | int | float | str) -> "Money":
        """From dollars (`"0.000412"`, or a provider's float, read through its shortest text)."""
        return cls(int((Decimal(str(amount)) * NANO).to_integral_value()))

    @property
    def dollars(self) -> Decimal:
        return Decimal(self.nusd) / NANO

    def __add__(self, other: "Money") -> "Money":
        return Money(self.nusd + other.nusd)


ZERO = Money(0)


@dataclass(frozen=True, slots=True)
class Usage:
    """What a call consumed: `units`, what the provider billed for it when it says (`cost`), and the model that
    answered as it names it (`served`), which may differ from the one asked (a router, an alias)."""

    units: Mapping[Unit, float] = field(default_factory=dict)
    cost: Money | None = None
    served: str | None = None

    def __add__(self, other: "Usage") -> "Usage":
        """Two reports of one call: units and billed amounts add up, the last model named is kept."""
        units = dict(self.units)
        for unit, quantity in other.units.items():
            units[unit] = units.get(unit, 0) + quantity
        cost = other.cost if self.cost is None else self.cost if other.cost is None else self.cost + other.cost
        return Usage(units, cost, other.served or self.served)


class Tally:
    """The reports of one call, gathered while it is `counting`."""

    def __init__(self) -> None:
        self.usage = Usage()
        self.reports = 0

    def add(self, usage: Usage) -> None:
        self.usage += usage
        self.reports += 1


_COUNTING: ContextVar[tuple[Tally, ...]] = ContextVar("nestor_metering", default=())


def report(usage: Usage) -> None:
    """Say what the call in progress consumed, once or in parts (they add up). Outside a call, nobody counts it."""
    for tally in _COUNTING.get():
        tally.add(usage)


@contextmanager
def counting(tally: Tally) -> Generator[Tally]:
    """Gather into `tally` what is reported until the block ends, as well as into every tally already open around it
    (a bench that records what the runtime meters)."""
    token = _COUNTING.set((*_COUNTING.get(), tally))
    try:
        yield tally
    finally:
        _COUNTING.reset(token)


async def counted[T](outputs: AsyncGenerator[T], tally: Tally) -> AsyncGenerator[T]:
    """`outputs`, a stream that reports as it goes, gathered into `tally`. Each step runs inside `counting` and leaves
    it before the output is handed over, so that nothing the reader does between two outputs is counted as the
    stream's."""
    try:
        while True:
            with counting(tally):
                try:
                    output = await anext(outputs)
                except StopAsyncIteration:
                    return
            yield output
    finally:
        with counting(tally):
            await outputs.aclose()

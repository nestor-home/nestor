"""What a call consumed reaches whoever counts it, and only it: the one way every model says what it used."""

from collections.abc import AsyncGenerator

from nestor.core import Money, Tally, Unit, Usage, counted, counting, report


async def test_a_stream_counts_what_it_reports_and_not_what_its_reader_does_between_two_outputs() -> None:
    async def stream() -> AsyncGenerator[str]:
        report(Usage({Unit.INPUT_TOKENS: 100}))
        yield "a"
        yield "b"
        report(Usage({Unit.OUTPUT_TOKENS: 7}, cost=Money.usd("0.0001"), served="m-2026"))

    tally, reader = Tally(), Tally()
    with counting(reader):  # the reader's own call: another model it asks while reading
        async for _ in counted(stream(), tally):
            report(Usage({Unit.INPUT_TOKENS: 1}))
    assert tally.usage == Usage({Unit.INPUT_TOKENS: 100, Unit.OUTPUT_TOKENS: 7}, Money(100_000), "m-2026")
    assert reader.usage.units == {Unit.INPUT_TOKENS: 102, Unit.OUTPUT_TOKENS: 7}, "open around it, it counts both"


async def test_a_stream_closed_early_still_counts_what_it_reports_while_closing() -> None:
    async def stream() -> AsyncGenerator[str]:
        try:
            yield "a"
            yield "b"
        finally:
            report(Usage({Unit.OUTPUT_TOKENS: 3}))

    tally = Tally()
    outputs = counted(stream(), tally)
    await anext(outputs)
    await outputs.aclose()
    assert tally.usage.units == {Unit.OUTPUT_TOKENS: 3}


def test_a_report_reaches_every_tally_open_around_it_and_none_after() -> None:
    outer, inner = Tally(), Tally()
    with counting(outer):
        with counting(inner):
            report(Usage({Unit.IMAGES: 1}))
        report(Usage({Unit.IMAGES: 1}))
    report(Usage({Unit.IMAGES: 1}))  # nobody counts: never an error
    assert (outer.usage.units, inner.usage.units) == ({Unit.IMAGES: 2}, {Unit.IMAGES: 1})


def test_money_adds_up_exactly_whatever_the_number_of_small_calls() -> None:
    total = Money(0)
    for _ in range(1000):
        total += Money.usd(0.0000001)  # a provider's float, a tenth of a micro-dollar
    assert total == Money.usd("0.0001")

"""A chat's answer, followed by pages: stopped, it counts each message the page received whole."""

import asyncio
from collections.abc import AsyncIterator

from nestor.modules.channels import LiveAnswer, MessageEnd, Reply


class Writing(Reply):
    """A message written in full, then a second one that never ends."""

    def __init__(self) -> None:
        self.heard: str | None = None

    async def __aiter__(self) -> AsyncIterator[str | MessageEnd]:
        yield "Je regarde."
        yield MessageEnd(last=False)
        yield "Voici"
        await asyncio.Event().wait()

    async def interrupt(self, heard: str) -> None:
        self.heard = heard


async def test_stopping_counts_each_message_shown_whole_and_ends_the_answer() -> None:
    reply = Writing()
    over: list[LiveAnswer] = []
    live = LiveAnswer(reply, over.append)
    parts = live.parts()
    seen = [await anext(parts) for _ in range(3)]

    await live.stop()

    assert len(seen) == 3
    assert reply.heard == "Je regarde. Voici", "the first message whole, then what came of the second"
    assert live.over and over == [live]

"""What every messaging channel shares: long answers cut where a reader expects a break, a wait for the platform as
long as it asked."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from nestor.adapters.channels.messaging import Incoming, MessagingChannel, split_text, utf16_length
from nestor.core import ProviderError
from nestor.modules.channels import Answer


def test_split_text_keeps_short_texts_whole() -> None:
    assert split_text("  Hello.  ", 100) == ["Hello."]
    assert split_text("", 100) == []


def test_split_text_prefers_a_paragraph_break_to_a_sentence_end() -> None:
    text = "One. Two.\n\nThree. Four."
    assert split_text(text, 20) == ["One. Two.", "Three. Four."]


def test_split_text_cuts_after_a_sentence_when_a_paragraph_is_too_long() -> None:
    text = "First sentence here. Second sentence there. Third one."
    assert split_text(text, 30) == ["First sentence here.", "Second sentence there.", "Third one."]


def test_split_text_cuts_a_word_longer_than_the_limit() -> None:
    assert split_text("abcdefghij", 4) == ["abcd", "efgh", "ij"]


def test_split_text_counts_as_the_platform_does() -> None:
    parts = split_text("🙂" * 5, 4, measure=utf16_length)  # an emoji is two UTF-16 units
    assert parts == ["🙂🙂", "🙂🙂", "🙂"]


class Quiet(MessagingChannel):
    name = "quiet"

    async def receive(self) -> AsyncIterator[Incoming]:
        return
        yield

    async def deliver(self, conversation: str, answer: Answer) -> None:
        pass


async def test_a_platform_that_asks_to_wait_is_left_alone_that_long(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(delay: float) -> None:
        slept.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    channel = Quiet("quiet", retry_delay_s=1.0)
    await channel.retry_later(ProviderError("discord", "429", transient=True, retry_after_s=30.0), 0)
    await channel.retry_later(ProviderError("discord", "502", transient=True), 1)
    assert slept == [30.0, 2.0]

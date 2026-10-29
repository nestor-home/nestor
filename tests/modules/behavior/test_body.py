"""The body contract, its recording double, and a body that would freeze the conversation."""

import time

import pytest

from nestor.modules.behavior import Behavior, Body, Expression
from nestor.testing.behavior import BodyContract, RecordingBody


class TestRecordingBody(BodyContract):
    def body(self) -> Body:
        return RecordingBody()


def test_the_timeline_keeps_changes_only() -> None:
    now = iter([1.0, 2.0, 3.0, 4.0])
    body = RecordingBody(clock=lambda: next(now))

    body.set_behavior(Behavior.LISTENING)
    body.set_behavior(Behavior.LISTENING)
    body.set_behavior(Behavior.SPEAKING)
    body.express(Expression.JOY)

    assert [b for _, b in body.behaviors] == [Behavior.LISTENING, Behavior.SPEAKING]
    assert body.behavior_at(0.5) is Behavior.IDLE
    assert body.behavior_at(2.5) is Behavior.SPEAKING
    assert body.expressions == [(3.0, Expression.JOY)]


class BlockingBody(RecordingBody):
    def beat(self) -> None:
        time.sleep(0.02)  # e.g. a synchronous motor command


async def test_the_contract_rejects_a_body_that_blocks() -> None:
    class Suite(BodyContract):
        def body(self) -> Body:
            return BlockingBody()

    with pytest.raises(AssertionError, match="intent took"):
        await Suite().test_intents_return_immediately()

"""The body contract on its recording double, and a body that would freeze the conversation."""

import time

import pytest

from nestor.modules.behavior import Body
from nestor.testing.behavior import BodyContract, RecordingBody


class TestRecordingBody(BodyContract):
    def body(self) -> Body:
        return RecordingBody()


class BlockingBody(RecordingBody):
    def beat(self) -> None:
        time.sleep(0.02)  # e.g. a synchronous motor command


async def test_the_contract_rejects_a_body_that_blocks() -> None:
    class Suite(BodyContract):
        def body(self) -> Body:
            return BlockingBody()

    with pytest.raises(AssertionError, match="intent took"):
        await Suite().test_intents_return_immediately()

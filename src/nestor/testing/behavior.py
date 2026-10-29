"""Test double and contract suite for the body port."""

import time
from collections.abc import Callable

from nestor.core import Capabilities
from nestor.modules.behavior import EXPRESSION, Behavior, Body, Expression


class RecordingBody(Body):
    """Records every intent with a timestamp from `clock` (monotonic seconds by default)."""

    name = "recording-body"
    capabilities = Capabilities.of(EXPRESSION)

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.behaviors: list[tuple[float, Behavior]] = []
        self.expressions: list[tuple[float, Expression]] = []
        self.beats: list[float] = []

    def set_behavior(self, behavior: Behavior) -> None:
        if not self.behaviors or self.behaviors[-1][1] is not behavior:
            self.behaviors.append((self._clock(), behavior))

    def express(self, expression: Expression) -> None:
        self.expressions.append((self._clock(), expression))

    def beat(self) -> None:
        self.beats.append(self._clock())

    def behavior_at(self, t: float) -> Behavior:
        current = Behavior.IDLE
        for at, behavior in self.behaviors:
            if at > t:
                break
            current = behavior
        return current


class BodyContract:
    """Behaviour every `Body` adapter must show. Mix into a `Test…` class and implement `body()`."""

    max_intent_s = 0.005  # an intent must never hold up the conversation loop

    def body(self) -> Body:
        raise NotImplementedError

    async def test_intents_return_immediately(self) -> None:
        async with self.body() as body:
            calls: list[Callable[[], None]] = [
                *(lambda b=b: body.set_behavior(b) for b in Behavior),
                *(lambda e=e: body.express(e) for e in Expression),
                *[body.beat] * 10,
            ]
            for call in calls:
                start = time.perf_counter()
                call()
                elapsed = time.perf_counter() - start
                assert elapsed < self.max_intent_s, f"intent took {elapsed * 1000:.1f} ms"

    async def test_close_is_idempotent_and_intents_stay_safe(self) -> None:
        body = self.body()
        await body.start()
        await body.close()
        await body.close()
        body.set_behavior(Behavior.SPEAKING)
        body.beat()

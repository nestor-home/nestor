"""The body port: what the behavior engine asks of any embodiment (robot, screen…).

The domain emits intentions; each body translates them into its own motion. Calls are
non-blocking: the body keeps the state and animates at its own pace, the conversation never
waits for a motor.
"""

from abc import ABC, abstractmethod

from nestor.core import Component
from nestor.modules.behavior.types import Behavior, Expression


class Body(Component, ABC):
    """Contract (checked by `nestor.testing.behavior.BodyContract`):
    - intent methods return immediately and never raise, even after the body was lost;
    - expressions and speech beats are sent when the matching audio is *played*, not generated;
    - `close` returns the body to a resting pose when it can, and is idempotent.
    """

    @abstractmethod
    def set_behavior(self, behavior: Behavior) -> None: ...

    @abstractmethod
    def express(self, expression: Expression) -> None: ...

    @abstractmethod
    def beat(self) -> None:
        """A word was just played: a light speech accent."""

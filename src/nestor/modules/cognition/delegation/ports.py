"""The executor port: long tasks handed to an external agent while the conversation goes on."""

from abc import ABC, abstractmethod

from nestor.core import Component
from nestor.modules.cognition.delegation.types import Outcome, Progress


class Executor(Component, ABC):
    """Runs one objective to completion and reports progress.

    `description` says what this executor can really do; the central agent's persona is built
    from it, so the assistant never promises more than what is plugged in.

    Contract (checked by `nestor.testing.cognition.ExecutorContract`):
    - a failure is returned as `Outcome.failed(...)`, never raised;
    - on cancellation the executor stops the remote work and returns `Outcome.cancelled()` only
      if the stop is confirmed, `Outcome.failed(...)` otherwise; it may also let `CancelledError`
      propagate when nothing remote was started. It never hangs.
    """

    description: str = ""

    @abstractmethod
    async def run(self, objective: str, progress: Progress) -> Outcome: ...

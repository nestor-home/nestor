"""The executor ports: long tasks handed to an external agent while the conversation goes on."""

import asyncio
from abc import ABC, abstractmethod

from nestor.core import Capabilities, Component, ProviderError
from nestor.modules.cognition.delegation.types import RESUME, Outcome, Progress


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


class RemoteExecutor(Executor, ABC):
    """An executor whose work runs elsewhere and outlives Nestor: its tasks survive restarts.

    The task manager submits, then follows; after a restart it follows the same reference again.
    Contract (checked by `nestor.testing.cognition.RemoteExecutorContract`):
    - `submit` raises `ProviderError` when the work is refused;
    - `follow` returns the outcome of a submitted run, and can be called again for the same run
      (after a restart) without starting it twice;
    - `stop` returns `True` only once the remote side confirmed the stop.
    """

    capabilities = Capabilities.of(RESUME)

    @abstractmethod
    async def submit(self, objective: str) -> str:
        """Start the work; returns its reference."""

    @abstractmethod
    async def follow(self, ref: str, progress: Progress) -> Outcome: ...

    @abstractmethod
    async def stop(self, ref: str) -> bool: ...

    async def run(self, objective: str, progress: Progress) -> Outcome:
        try:
            ref = await self.submit(objective)
        except ProviderError as error:
            return Outcome.failed(str(error))
        progress.attach(ref)
        try:
            return await self.follow(ref, progress)
        except asyncio.CancelledError:
            confirmed = await asyncio.shield(self.stop(ref))
            return Outcome.cancelled() if confirmed else Outcome.failed("stop requested, not confirmed")

"""The executor ports: tasks handed to an external agent, a turn at a time, while the conversation goes on."""

import asyncio
from abc import ABC, abstractmethod

from nestor.core import Capabilities, Component, ProviderError
from nestor.modules.cognition.delegation.types import RESUME, Assignment, NestorAccess, NestorTools, Outcome, Progress


class Executor(Component, ABC):
    """Runs one turn of a task to its end and reports progress.

    `description` says what this executor can really do; the central agent's persona is built from it, so the
    assistant never promises more than what is plugged in. `sensitive`: it acts with real power (a server, a
    network): starting or directing its tasks from a shared device asks the person to confirm in writing.
    `archive_after_days`: a task left ready that long is put away (`None`: never).

    Contract (checked by `nestor.testing.cognition.ExecutorContract`):
    - a failure is returned as `Outcome.failed(...)`, never raised;
    - a turn that needs its owner ends with `Outcome.asked(question)`;
    - with `CONTINUE`, the outcome names its `session`, and a turn given that session goes on in it: the executor
      remembers the turns before;
    - with `STEER`, the turn attaches its handle (`progress.attach`) and `steer(handle, instruction)` brings the
      instruction into it while it works, `True` once the executor took it;
    - on cancellation the executor stops the work and returns `Outcome.stopped()` only if the stop is confirmed,
      `Outcome.failed(...)` otherwise; it may also let `CancelledError` propagate when nothing remote was started.
      It never hangs.
    """

    description: str = ""
    nestor_tools: NestorTools = NestorTools.NONE  # how it reaches Nestor's MCP server while it works
    sensitive: bool = False
    archive_after_days: int | None = 30

    def setup(self, access: NestorAccess) -> str | None:
        """What to add to its own configuration to reach Nestor's MCP server with this key, for an executor that
        declares the server itself (`NestorTools.CONFIGURED`); `None` when there is nothing to add."""
        return None

    @abstractmethod
    async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
        """Carry out `assignment.brief()`; with `assignment.access`, Nestor's MCP server is wired in for it."""

    async def steer(self, handle: str, instruction: str) -> bool:
        """Bring `instruction` into the turn `handle` names while it works; `False` when it could not (no `STEER`,
        the turn ended meanwhile)."""
        return False


class RemoteExecutor(Executor, ABC):
    """An executor whose work runs elsewhere and outlives Nestor: its turns survive restarts.

    The task manager submits, then follows; after a restart it follows the same reference again.
    Contract (checked by `nestor.testing.cognition.RemoteExecutorContract`):
    - `submit` raises `ProviderError` when the work is refused;
    - `follow` returns the outcome of a submitted turn, and can be called again for the same one (after a restart)
      without starting it twice;
    - `stop` returns `True` only once the remote side confirmed the stop.
    """

    capabilities = Capabilities.of(RESUME)

    @abstractmethod
    async def submit(self, assignment: Assignment) -> str:
        """Start the turn; returns its reference, which is also its handle."""

    @abstractmethod
    async def follow(self, ref: str, progress: Progress) -> Outcome: ...

    @abstractmethod
    async def stop(self, ref: str) -> bool: ...

    def session_of(self, ref: str) -> str | None:
        """The session the turn `ref` works in, as its outcome would name it: what a turn stopped before it reported
        still lets the next one continue (a Codex thread). `None` when the reference does not tell."""
        return None

    async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
        try:
            ref = await self.submit(assignment)
        except ProviderError as error:
            return Outcome.failed(str(error), session=assignment.session)
        progress.attach(ref)
        try:
            return await self.follow(ref, progress)
        except asyncio.CancelledError:
            confirmed = await asyncio.shield(self.stop(ref))
            session = assignment.session or self.session_of(ref)
            return Outcome.stopped(session=session) if confirmed else Outcome.failed("stop not confirmed")

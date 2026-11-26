"""The executor ports: tasks handed to an external agent, a turn at a time, while the conversation goes on."""

import asyncio
from abc import ABC, abstractmethod

from nestor.core import Capabilities, Component, ProviderError
from nestor.modules.cognition.delegation.types import (
    RESUME,
    Assignment,
    Handle,
    NestorAccess,
    NestorTools,
    Outcome,
    Progress,
)


class SessionLost(ProviderError):
    """The session an assignment names is one the executor no longer knows (deleted, expired): nothing started."""


class Executor(Component, ABC):
    """Runs one turn of a task to its end and reports progress.

    `description` says what this executor can really do; the central agent's persona is built from it, so the
    assistant never promises more than what is plugged in. `sensitive`: it acts with real power (a server, a
    network): starting or directing its tasks from a shared device asks the person to confirm in writing.
    `archive_after_days`: a task left ready that long is put away (`None`: never).

    Contract (checked by `nestor.testing.cognition.ExecutorContract`):
    - a failure is returned as `Outcome.failed(...)`, never raised;
    - a turn that needs its owner ends with `Outcome.asked(question)`;
    - with `CONTINUE`, the turn names its session, as it attaches (`progress.attach(ref, session=…)`) or in its
      outcome, and a turn given that session goes on in it: the executor remembers the turns before; a turn given a
      session it no longer knows ends with `Outcome.lost(...)`, when it can tell;
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

    A turn is submitted, attached, then followed; after a restart its reference is followed again (`resume`). A
    turn cancelled while Nestor closes (`progress.detached`) is left working; cancelled otherwise, it is stopped.
    Contract (checked by `nestor.testing.cognition.RemoteExecutorContract`):
    - `submit` raises `ProviderError` when the work is refused, `SessionLost` when the session it names is unknown;
    - `follow` returns the outcome of a submitted turn, and can be called again for the same one (after a restart)
      without starting it twice;
    - `stop` returns `True` only once the remote side confirmed the stop.
    """

    capabilities = Capabilities.of(RESUME)

    @abstractmethod
    async def submit(self, assignment: Assignment) -> Handle:
        """Start the turn; returns its reference, which is also its handle, and its session when it is known."""

    @abstractmethod
    async def follow(self, ref: str, progress: Progress) -> Outcome: ...

    @abstractmethod
    async def stop(self, ref: str) -> bool: ...

    async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
        try:
            handle = await self.submit(assignment)
        except SessionLost as error:
            return Outcome.lost(str(error))
        except ProviderError as error:
            return Outcome.failed(str(error))
        progress.attach(handle.ref, session=handle.session)
        return await self.resume(handle.ref, progress)

    async def resume(self, ref: str, progress: Progress) -> Outcome:
        """Follow the turn `ref` to its end; cancelled, stop it, unless Nestor is closing (`progress.detached`): then
        the cancellation goes through and the turn keeps working, to be followed again."""
        try:
            return await self.follow(ref, progress)
        except asyncio.CancelledError:
            if progress.detached:
                raise
            confirmed = await asyncio.shield(self.stop(ref))
            return Outcome.stopped() if confirmed else Outcome.failed("stop not confirmed")

"""Test double and contract suite for the executor port."""

import asyncio
from dataclasses import dataclass, field

from nestor.core import ProviderError, new_id
from nestor.modules.cognition import Executor, Outcome, Progress, RemoteExecutor, TaskStatus


class ScriptedExecutor(Executor):
    """Finishes after `duration_s` with a result or an error; confirms a stop unless told otherwise."""

    name = "scripted-executor"
    description = "carry out scripted test tasks"

    def __init__(
        self, result: str = "done", *, duration_s: float = 0.0, error: str | None = None, confirms_stop: bool = True
    ):
        self._result, self._duration_s, self._error, self._confirms_stop = result, duration_s, error, confirms_stop
        self.objectives: list[str] = []
        self.cancelled = 0

    async def run(self, objective: str, progress: Progress) -> Outcome:
        self.objectives.append(objective)
        progress("started")
        try:
            await asyncio.sleep(self._duration_s)
        except asyncio.CancelledError:
            self.cancelled += 1
            return Outcome.cancelled() if self._confirms_stop else Outcome.failed("stop requested, not confirmed")
        return Outcome.failed(self._error) if self._error else Outcome.completed(self._result)


class ExecutorContract:
    """Behaviour every `Executor` adapter must show. Implement `executor()`, `slow_executor()` and
    `failing_executor()`."""

    cancel_timeout_s = 20.0

    def executor(self) -> Executor:
        raise NotImplementedError

    def slow_executor(self) -> Executor:
        """An executor whose task runs long enough to be cancelled midway."""
        raise NotImplementedError

    def failing_executor(self) -> Executor:
        """An executor whose task fails (remote error, refused objective…)."""
        raise NotImplementedError

    def objective(self) -> str:
        return "Dis bonjour."

    async def test_completes_with_a_result(self) -> None:
        async with self.executor() as executor:
            outcome = await executor.run(self.objective(), Progress())
        assert outcome.status is TaskStatus.COMPLETED, outcome
        assert outcome.result

    async def test_failure_is_returned_not_raised(self) -> None:
        async with self.failing_executor() as executor:
            outcome = await executor.run(self.objective(), Progress())
        assert outcome.status is TaskStatus.FAILED and outcome.error, outcome

    async def test_cancellation_ends_without_hanging(self) -> None:
        async with self.slow_executor() as executor:
            job = asyncio.create_task(executor.run(self.objective(), Progress()))
            await asyncio.sleep(0.05)
            job.cancel()
            # `wait`, not `wait_for`: a stubborn executor must fail the suite, not hang it.
            done, _ = await asyncio.wait({job}, timeout=self.cancel_timeout_s)
            assert done, f"executor still running {self.cancel_timeout_s}s after cancellation"
            if job.cancelled():
                return  # nothing remote was started: local cancellation is enough
            outcome = job.result()
        assert outcome.status in (TaskStatus.CANCELLED, TaskStatus.FAILED), outcome


@dataclass(slots=True)
class RemoteRun:
    objective: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    outcome: Outcome | None = None
    follows: int = 0


class FakeRemote:
    """The remote service behind `ScriptedRemoteExecutor`. Share one between executor instances to
    play a Nestor restart: the runs live on."""

    def __init__(self) -> None:
        self.runs: dict[str, RemoteRun] = {}

    def finish(self, ref: str, outcome: Outcome) -> None:
        run = self.runs[ref]
        if run.outcome is None:
            run.outcome = outcome
            run.done.set()


class ScriptedRemoteExecutor(RemoteExecutor):
    """Remote work that completes after `duration_s` (never, if `None`: finish it with `remote.finish`)."""

    name = "scripted-remote"
    description = "carry out scripted remote tasks"

    def __init__(
        self,
        remote: FakeRemote | None = None,
        *,
        result: str = "done",
        duration_s: float | None = 0.0,
        refuses: bool = False,
        confirms_stop: bool = True,
    ) -> None:
        self.remote = remote or FakeRemote()
        self._result, self._duration_s = result, duration_s
        self._refuses, self._confirms_stop = refuses, confirms_stop
        self._timers: set[asyncio.Task[None]] = set()

    async def submit(self, objective: str) -> str:
        if self._refuses:
            raise ProviderError(self.name, "objective refused", transient=False)
        ref = new_id()[:8]
        self.remote.runs[ref] = RemoteRun(objective)
        if self._duration_s is not None:
            timer = asyncio.create_task(self._complete(ref, self._duration_s))
            self._timers.add(timer)
            timer.add_done_callback(self._timers.discard)
        return ref

    async def follow(self, ref: str, progress: Progress) -> Outcome:
        run = self.remote.runs[ref]
        run.follows += 1
        progress("working")
        await run.done.wait()
        assert run.outcome is not None
        return run.outcome

    async def stop(self, ref: str) -> bool:
        if self._confirms_stop:
            self.remote.finish(ref, Outcome.cancelled())
        return self._confirms_stop

    async def _complete(self, ref: str, after_s: float) -> None:
        await asyncio.sleep(after_s)
        self.remote.finish(ref, Outcome.completed(self._result))


class RemoteExecutorContract(ExecutorContract):
    """What a `RemoteExecutor` adds to the executor contract: its runs can be followed again."""

    def executor(self) -> RemoteExecutor:
        raise NotImplementedError

    async def test_a_run_can_be_followed_again_without_starting_twice(self) -> None:
        async with self.executor() as executor:
            ref = await executor.submit(self.objective())
            first = await executor.follow(ref, Progress())
        async with self.executor() as restarted:
            again = await restarted.follow(ref, Progress())
        assert first == again and first.status is TaskStatus.COMPLETED, (first, again)

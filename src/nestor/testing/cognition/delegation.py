"""Test double and contract suite for the executor port."""

import asyncio

from nestor.modules.cognition import Executor, Outcome, Progress, TaskStatus


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
            outcome = await executor.run(self.objective(), lambda _: None)
        assert outcome.status is TaskStatus.COMPLETED, outcome
        assert outcome.result

    async def test_failure_is_returned_not_raised(self) -> None:
        async with self.failing_executor() as executor:
            outcome = await executor.run(self.objective(), lambda _: None)
        assert outcome.status is TaskStatus.FAILED and outcome.error, outcome

    async def test_cancellation_ends_without_hanging(self) -> None:
        async with self.slow_executor() as executor:
            job = asyncio.create_task(executor.run(self.objective(), lambda _: None))
            await asyncio.sleep(0.05)
            job.cancel()
            # `wait`, not `wait_for`: a stubborn executor must fail the suite, not hang it.
            done, _ = await asyncio.wait({job}, timeout=self.cancel_timeout_s)
            assert done, f"executor still running {self.cancel_timeout_s}s after cancellation"
            if job.cancelled():
                return  # nothing remote was started: local cancellation is enough
            outcome = job.result()
        assert outcome.status in (TaskStatus.CANCELLED, TaskStatus.FAILED), outcome

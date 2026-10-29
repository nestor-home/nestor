"""The executor contract, its scripted double, and executors the contract must reject or accept."""

import asyncio

import pytest

from nestor.modules.cognition import Executor, Outcome, Progress
from nestor.testing.cognition import ExecutorContract, ScriptedExecutor


class TestScriptedExecutor(ExecutorContract):
    def executor(self) -> Executor:
        return ScriptedExecutor("Il fera 18 degrés.")

    def slow_executor(self) -> Executor:
        return ScriptedExecutor(duration_s=30)

    def failing_executor(self) -> Executor:
        return ScriptedExecutor(error="service météo injoignable")


class StubbornExecutor(Executor):
    """Ignores the stop request and finishes its work anyway."""

    async def run(self, objective: str, progress: Progress) -> Outcome:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await asyncio.sleep(10)
        return Outcome.completed("finished anyway")


class LocalExecutor(Executor):
    """Works locally: letting the cancellation propagate is a valid way to stop."""

    async def run(self, objective: str, progress: Progress) -> Outcome:
        await asyncio.sleep(10)
        return Outcome.completed("done")


class RaisingExecutor(Executor):
    async def run(self, objective: str, progress: Progress) -> Outcome:
        raise RuntimeError("remote agent crashed")


async def test_the_executor_contract_rejects_hangs_and_raised_failures() -> None:
    class Suite(ExecutorContract):
        cancel_timeout_s = 0.2

        def slow_executor(self) -> Executor:
            return StubbornExecutor()

        def failing_executor(self) -> Executor:
            return RaisingExecutor()

    with pytest.raises(AssertionError, match="still running"):
        await Suite().test_cancellation_ends_without_hanging()
    with pytest.raises(RuntimeError, match="crashed"):
        await Suite().test_failure_is_returned_not_raised()


async def test_the_executor_contract_accepts_a_local_cancellation() -> None:
    class Suite(ExecutorContract):
        def slow_executor(self) -> Executor:
            return LocalExecutor()

    await Suite().test_cancellation_ends_without_hanging()

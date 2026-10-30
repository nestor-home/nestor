"""Durable tasks: delegated from the conversation, followed in the background, resumed after a restart."""

import asyncio
from typing import Any

import pytest

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition import (
    Executor,
    Notify,
    Outcome,
    Progress,
    TaskAttached,
    TaskCancelRequested,
    TaskEnded,
    TaskProgressed,
    TaskStarted,
    TaskStatus,
)
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import INTERRUPTED, TaskManager
from nestor.modules.cognition.tools import ToolContext
from nestor.modules.journal import Journal
from nestor.testing.cognition import (
    FakeRemote,
    RemoteExecutorContract,
    ScriptedExecutor,
    ScriptedRemoteExecutor,
)
from nestor.testing.journal import MemoryEventLog

VOICE = Address("voice", "salon")
MATHIS = PersonId("mathis")


class TestScriptedRemoteExecutor(RemoteExecutorContract):
    def setup_method(self) -> None:
        self.remote = FakeRemote()

    def executor(self) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(self.remote, result="Il fera 18 degrés.")

    def slow_executor(self) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(duration_s=None)

    def failing_executor(self) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(refuses=True)


def data(output: object) -> dict[str, Any]:
    assert isinstance(output, dict)
    return output


class Stubborn(ScriptedRemoteExecutor):
    name = "stubborn"


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


async def test_a_delegated_task_runs_in_the_background_and_is_logged(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor("Trois soucis trouvés.", duration_s=0.01)]) as tasks:
        task = await tasks.delegate("Analyse le dépôt", origin=VOICE, requested_by=MATHIS, notify=Notify.MESSAGE)
        assert task.status is TaskStatus.RUNNING
        outcome = await tasks.wait(task.id)

    assert outcome == Outcome.completed("Trois soucis trouvés.")
    started, ended = (await journal.history(TaskStarted))[0], (await journal.history(TaskEnded))[0]
    assert (started.origin, started.requested_by, started.notify) == (VOICE, MATHIS, Notify.MESSAGE)
    assert ended.status is TaskStatus.COMPLETED and ended.result == "Trois soucis trouvés."
    assert [p.step for p in await journal.history(TaskProgressed)] == ["started"]


async def test_progress_is_logged_before_the_end(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor()]) as tasks:
        await tasks.wait((await tasks.delegate("x", origin=VOICE)).id)
    types = [e.event_type for e in await journal.history(TaskStarted, TaskProgressed, TaskEnded)]
    assert types == ["task.started", "task.progress", "task.ended"]


async def test_remote_work_survives_a_restart_and_is_not_started_twice(journal: Journal) -> None:
    remote = FakeRemote()
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)]) as tasks:
        task = await tasks.delegate("Long travail", origin=VOICE)
        await asyncio.sleep(0.01)
    (ref,) = remote.runs
    assert remote.runs[ref].outcome is None, "a restart must not stop remote work"

    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)]) as restarted:
        remote.finish(ref, Outcome.completed("fini pendant le redémarrage"))
        outcome = await restarted.wait(task.id)

    assert outcome.result == "fini pendant le redémarrage"
    assert len(remote.runs) == 1 and remote.runs[ref].follows == 2
    assert [e.ref for e in await journal.history(TaskAttached)] == [ref]


async def test_local_work_cut_by_a_restart_is_reported_not_lost(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor(duration_s=30)]) as tasks:
        task = await tasks.delegate("Travail local", origin=VOICE)
        await asyncio.sleep(0.01)
    # the shutdown stopped it cleanly; now play a crash: a task the journal still sees running
    await journal.publish(
        TaskStarted(source="test", task_id="crashed", objective="x", executor="scripted-executor", origin=VOICE)
    )
    async with TaskManager(journal, [ScriptedExecutor()]) as restarted:
        assert restarted.tasks[task.id].status is TaskStatus.CANCELLED
        assert restarted.tasks["crashed"].outcome == Outcome.failed(INTERRUPTED)
    assert [e.task_id for e in await journal.history(TaskEnded)] == [task.id, "crashed"]


async def test_a_cancellation_is_confirmed_or_reported_unconfirmed(journal: Journal) -> None:
    stubborn = Stubborn(duration_s=None, confirms_stop=False)
    async with TaskManager(journal, [ScriptedRemoteExecutor(duration_s=None), stubborn]) as tasks:
        polite = await tasks.delegate("a", origin=VOICE)
        hard = await tasks.delegate("b", origin=VOICE, executor="stubborn")
        await asyncio.sleep(0.01)
        assert (await tasks.cancel(polite.id)).status is TaskStatus.CANCELLED
        assert (await tasks.cancel(hard.id)).error == "stop requested, not confirmed"
        assert (await tasks.cancel(polite.id)).status is TaskStatus.CANCELLED  # already over
        assert (await tasks.cancel("nope")).error == "unknown task 'nope'"
    assert len(await journal.history(TaskCancelRequested)) == 2


async def test_an_executor_that_hangs_on_cancel_is_reported(journal: Journal) -> None:
    class Slow(Executor):
        """Takes far longer to stop than the manager is willing to wait."""

        name = "slow-to-stop"

        async def run(self, objective: str, progress: Progress) -> Outcome:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await asyncio.sleep(0.2)
            return Outcome.cancelled()

    async with TaskManager(journal, [Slow()], cancel_timeout_s=0.01) as tasks:
        task = await tasks.delegate("x", origin=VOICE)
        await asyncio.sleep(0.01)
        assert (await tasks.cancel(task.id)).error == "stop requested, not confirmed by the executor"
        assert (await tasks.wait(task.id)).status is TaskStatus.CANCELLED


async def test_work_stopped_before_it_reached_the_executor_ends_cancelled(journal: Journal) -> None:
    class Local(Executor):
        """Lets the cancellation through: nothing remote was started."""

        name = "local"

        async def run(self, objective: str, progress: Progress) -> Outcome:
            await asyncio.sleep(10)
            return Outcome.completed("never")

    class SlowSubmit(ScriptedRemoteExecutor):
        name = "slow-submit"

        async def submit(self, objective: str) -> str:
            await asyncio.sleep(10)
            return "never"

    async with TaskManager(journal, [Local(), SlowSubmit()]) as tasks:
        ids = [(await tasks.delegate("x", origin=VOICE, executor=name)).id for name in ("local", "slow-submit")]
        await asyncio.sleep(0.01)
        outcomes = [await tasks.cancel(i) for i in ids]
    assert [o.status for o in outcomes] == [TaskStatus.CANCELLED, TaskStatus.CANCELLED]


async def test_failures_end_the_task_without_breaking_the_assistant(journal: Journal) -> None:
    class Crashing(Executor):
        name = "crashing"

        async def run(self, objective: str, progress: Progress) -> Outcome:
            raise RuntimeError("remote agent crashed")

    class Lost(ScriptedRemoteExecutor):
        name = "lost"

        async def follow(self, ref: str, progress: Progress) -> Outcome:
            raise ConnectionError("stream dropped")

    executors = [Crashing(), ScriptedRemoteExecutor(refuses=True), Lost()]
    async with TaskManager(journal, executors) as tasks:
        ids = [(await tasks.delegate("x", origin=VOICE, executor=e.name)).id for e in executors]
        errors = [(await tasks.wait(i)).error for i in ids]
    assert errors == [
        "RuntimeError: remote agent crashed",
        "scripted-remote: objective refused",
        "ConnectionError: stream dropped",
    ]


async def test_delegating_needs_a_started_manager_and_a_known_executor(journal: Journal) -> None:
    with pytest.raises(ContractError, match="must be started"):
        await TaskManager(journal, [ScriptedExecutor()]).delegate("x", origin=VOICE)
    async with TaskManager(journal, []) as none:
        with pytest.raises(ContractError, match="no executor is plugged in"):
            await none.delegate("x", origin=VOICE)
    async with TaskManager(journal, [ScriptedExecutor()]) as tasks:
        with pytest.raises(ContractError, match="no executor named 'codex'"):
            await tasks.delegate("x", origin=VOICE, executor="codex")


async def test_the_agent_delegates_follows_and_cancels_through_its_tools(journal: Journal) -> None:
    context = ToolContext(address=VOICE, person=MATHIS)
    async with TaskManager(journal, [ScriptedRemoteExecutor(duration_s=None)]) as tasks:
        tools = {t.name: t for t in Delegation(tasks).tools()}
        started = data(
            await tools["delegate_task"].run({"objective": "Cherche un resto", "notify": "message"}, context)
        )
        task_id = str(started["task_id"])
        status = data(await tools["task_status"].run({}, context))
        cancelled = await tools["cancel_task"].run({"task_id": task_id}, context)
        after = data(await tools["task_status"].run({}, context))

    assert tasks.tasks[task_id].notify is Notify.MESSAGE and tasks.tasks[task_id].requested_by == MATHIS
    assert [t["task_id"] for t in status["running"]] == [task_id]
    assert cancelled == {"stopped": True, "status": "cancelled"}
    assert after["recently_finished"][0]["status"] == "cancelled"


async def test_the_delegation_tools_refuse_bad_arguments(journal: Journal) -> None:
    from nestor.modules.cognition.tools import ToolFailed

    context = ToolContext(address=VOICE)
    async with TaskManager(journal, [ScriptedExecutor(), ScriptedRemoteExecutor()]) as tasks:
        tools = {t.name: t for t in Delegation(tasks).tools()}
        assert "executor" in data(tools["delegate_task"].spec.parameters["properties"])
        with pytest.raises(ToolFailed, match="notify must be one of"):
            await tools["delegate_task"].run({"objective": "x", "notify": "pigeon"}, context)
        with pytest.raises(ToolFailed, match="no executor named"):
            await tools["delegate_task"].run({"objective": "x", "executor": "codex"}, context)


async def test_the_instructions_say_what_executors_can_do_and_what_runs(journal: Journal) -> None:
    async with TaskManager(journal, []) as none:
        assert Delegation(none).tools() == ()
        assert "No executor is plugged in" in str(await Delegation(none).context(None, VOICE))
    async with TaskManager(journal, [ScriptedRemoteExecutor(duration_s=None)]) as tasks:
        await tasks.delegate("Réserver un resto", origin=VOICE)
        section = str(await Delegation(tasks).context(None, VOICE))
    assert "scripted-remote: carry out scripted remote tasks" in section
    assert "Réserver un resto" in section

"""Durable tasks: delegated from the conversation, followed in the background, resumed after a restart."""

import asyncio
from typing import Any

import pytest

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address, Attachment, AttachmentKind, Medium
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
from nestor.modules.cognition.delegation import Assignment, ExecutorKeys, NestorTools
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import INTERRUPTED, TaskManager
from nestor.modules.cognition.tools import ToolContext
from nestor.modules.conversation import Attached, Conversations, TurnContext
from nestor.modules.identity import Speaker
from nestor.modules.journal import BlobRef, Journal
from nestor.testing.cognition import (
    FakeRemote,
    RemoteExecutorContract,
    ScriptedExecutor,
    ScriptedRemoteExecutor,
)
from nestor.testing.connectors import MemoryVault
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

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
    async with TaskManager(journal, [ScriptedExecutor("Trois soucis trouvés.")]) as tasks:
        task = await tasks.delegate("Analyse le dépôt", origin=VOICE, requested_by=MATHIS, notify=Notify.MESSAGE)
        assert task.status is TaskStatus.RUNNING
        outcome = await tasks.wait(task.id)

    assert outcome == Outcome.completed("Trois soucis trouvés.")
    started, ended = (await journal.history(TaskStarted))[0], (await journal.history(TaskEnded))[0]
    assert (started.origin, started.requested_by, started.notify) == (VOICE, MATHIS, Notify.MESSAGE)
    assert ended.status is TaskStatus.COMPLETED and ended.result == "Trois soucis trouvés."
    logged = await journal.history(TaskStarted, TaskProgressed, TaskEnded)
    assert [e.event_type for e in logged] == ["task.started", "task.progress", "task.ended"], "progress before the end"
    assert [p.step for p in logged if isinstance(p, TaskProgressed)] == ["started"]


async def test_the_files_a_task_made_are_kept_and_one_that_cannot_be_is_said_not_lost(journal: Journal) -> None:
    class FullDisk(MemoryBlobStore):
        async def put(self, data: bytes, media_type: str) -> BlobRef:
            if data == b"too much":
                raise OSError(28, "No space left on device")
            return await super().put(data, media_type)

    class Writer(Executor):
        name = "writer"

        async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
            made = [Attachment(kind=AttachmentKind.FILE, data=d, media_type="text/plain", name=n) for n, d in FILES]
            return Outcome.completed("Écrits.", tuple(made))

    FILES = [("a.txt", b"kept"), ("b.txt", b"too much")]
    blobs = FullDisk()
    async with TaskManager(journal, [Writer()], blobs=blobs) as tasks:
        task = await tasks.delegate("Écris-les", origin=VOICE, requested_by=MATHIS)
        outcome = await tasks.wait(task.id)
    [ended] = await journal.history(TaskEnded)
    assert [blobs.blobs[f.digest] for f in ended.files] == [b"kept"]
    assert ended.result == outcome.result == "Écrits.\nFiles not kept: b.txt (OSError)"
    assert outcome.files == (), "the bytes live in the blob store, not in the task"
    async with TaskManager(Journal(MemoryEventLog()), [Writer()]) as nowhere:
        lost = await nowhere.wait((await nowhere.delegate("Écris-les", origin=VOICE)).id)
    assert lost.result == "Écrits.\nFiles not kept: a.txt (nowhere to keep it); b.txt (nowhere to keep it)"


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

        async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
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

        async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
            await asyncio.sleep(10)
            return Outcome.completed("never")

    class SlowSubmit(ScriptedRemoteExecutor):
        name = "slow-submit"

        async def submit(self, assignment: Assignment) -> str:
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

        async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
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
    context = ToolContext(address=VOICE, speaker=Speaker.account(MATHIS))
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


async def test_the_files_sent_in_the_conversation_go_with_the_task_but_not_what_was_said_aloud() -> None:
    journal, blobs, remote = Journal(MemoryEventLog()), MemoryBlobStore(), FakeRemote()
    chat, mathis = Address("telegram", "42"), Speaker.account(MATHIS)
    devis, other, photo, voice = [
        await blobs.put(data, media)
        for data, media in [
            (b"%PDF devis", "application/pdf"),
            (b"%PDF autre", "application/pdf"),
            (b"jpeg", "image/jpeg"),
            (b"ogg", "audio/ogg"),
        ]
    ]
    conversations = Conversations(journal, ends_after_s=lambda address, medium: 3600)
    first = await conversations.turn(chat, Medium.WRITTEN)
    sent = (
        Attached(AttachmentKind.FILE, devis, "../devis.pdf"),
        Attached(AttachmentKind.VOICE, voice),
        Attached(AttachmentKind.IMAGE, photo),
    )
    await first.said("Voilà le devis", Medium.WRITTEN, mathis, sent)
    second = await conversations.turn(chat, Medium.WRITTEN)
    sent = (Attached(AttachmentKind.FILE, other, "devis.pdf"), Attached(AttachmentKind.FILE, devis, "devis.pdf"))
    await second.said("Et l'autre", Medium.WRITTEN, mathis, sent)
    context = ToolContext(address=chat, speaker=mathis, exchange=second.exchange)
    expected = [("devis.pdf", b"%PDF devis"), ("file.jpg", b"jpeg"), ("devis (2).pdf", b"%PDF autre")]
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)], blobs=blobs) as tasks:
        tool = next(t for t in Delegation(tasks).tools() if t.name == "delegate_task")
        task_id = str(data(await tool.run({"objective": "Compare les devis"}, context))["task_id"])
        await asyncio.sleep(0.01)
        [run] = remote.runs.values()
        assert [(f.name, f.data) for f in run.assignment.files] == expected, "plain names, none twice, no voice"
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)], blobs=blobs) as tasks:
        assert [g.name for g in tasks.tasks[task_id].given] == [name for name, _ in expected], "kept by the journal"
        await tasks.cancel(task_id)


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
        assert "No executor is plugged in" in Delegation(none).guidance()
        assert (
            await Delegation(none).context(
                TurnContext(person=None, speaker=Speaker.unknown(), address=VOICE, said=None)
            )
            == {}
        )
    async with TaskManager(journal, [ScriptedRemoteExecutor(duration_s=None)]) as tasks:
        await tasks.delegate("Réserver un resto", origin=VOICE)
        guidance, running = (
            Delegation(tasks).guidance(),
            str(
                await Delegation(tasks).context(
                    TurnContext(person=None, speaker=Speaker.unknown(), address=VOICE, said=None)
                )
            ),
        )
    assert "scripted-remote: carry out scripted remote tasks" in guidance and "Réserver" not in guidance
    assert "Réserver un resto" in running


class Reaching(ScriptedRemoteExecutor):
    """A remote executor that reaches Nestor's MCP server with what Nestor passes it."""

    nestor_tools = NestorTools.PASSED


async def keys_for(journal: Journal, *executors: str) -> ExecutorKeys:
    keys = ExecutorKeys(journal, MemoryVault(), "https://nestor.example/mcp", executors)
    await keys.start()
    return keys


async def test_a_task_for_an_executor_that_reaches_nestor_gets_a_capability_good_for_it_while_it_runs() -> None:
    journal, remote = Journal(MemoryEventLog()), FakeRemote()
    reaching, plain = Reaching(remote, duration_s=None), ScriptedRemoteExecutor(FakeRemote(), duration_s=None)
    reaching.name, plain.name = "codex", "hermes"
    keys = await keys_for(journal, "codex", "hermes")
    async with TaskManager(journal, [reaching, plain], keys=keys) as tasks:
        task = await tasks.delegate("Corrige le test", origin=VOICE, executor="codex")
        other = await tasks.delegate("Cherche un vol", origin=VOICE, executor="hermes")
        await asyncio.sleep(0.01)
        [given] = [r.assignment for r in remote.runs.values()]
        assert given.task and given.task.startswith("nstt_") and given.access is not None
        assert given.access.url == "https://nestor.example/mcp" and keys.caller(given.access.key) == "codex"
        assert given.task in given.brief() and "task_brief" in given.brief()
        assert [r.assignment.task for r in plain.remote.runs.values()] == [None], "it cannot reach"
        assert await tasks.admit("codex", given.task, "task_brief") is task
        assert await tasks.admit("hermes", given.task, "task_brief") is None, "another executor's task"
        assert await tasks.admit("codex", "nstt_guessed", "task_brief") is None
        [started] = [e for e in await journal.history(TaskStarted) if e.task_id == task.id]
        assert started.capability and given.task not in str(started.to_record()), "only its digest is journaled"
        remote.finish(next(iter(remote.runs)), Outcome.completed("ok"))
        await tasks.wait(task.id)
        assert await tasks.admit("codex", given.task, "task_brief") is None, "it ended"
        await tasks.cancel(other.id)


async def test_a_capability_still_works_for_a_remote_task_followed_again_after_a_restart() -> None:
    journal, remote = Journal(MemoryEventLog()), FakeRemote()
    executor = Reaching(remote, duration_s=None)
    executor.name = "codex"
    async with TaskManager(journal, [executor], keys=await keys_for(journal, "codex")) as tasks:
        task = await tasks.delegate("Corrige le test", origin=VOICE)
        await asyncio.sleep(0.01)
    [run] = remote.runs.values()
    assert run.assignment.task
    again = Reaching(remote, duration_s=None)
    again.name = "codex"
    async with TaskManager(journal, [again], keys=await keys_for(journal, "codex")) as restarted:
        found = await restarted.admit("codex", run.assignment.task, "task_brief")
        assert found is not None and found.id == task.id
        remote.finish(next(iter(remote.runs)), Outcome.completed("ok"))
        await restarted.wait(task.id)


async def test_a_file_an_executor_hands_back_while_it_works_goes_with_the_result() -> None:
    journal, blobs, remote = Journal(MemoryEventLog()), MemoryBlobStore(), FakeRemote()
    executor = Reaching(remote, duration_s=None)
    async with TaskManager(journal, [executor], blobs=blobs) as tasks:
        task = await tasks.delegate("Écris le devis", origin=VOICE)
        await asyncio.sleep(0.01)
        pdf = Attachment(
            kind=AttachmentKind.FILE, data=b"%PDF-1.7 devis", media_type="application/pdf", name="devis.pdf"
        )
        kept = await tasks.add_file(task, pdf)
        remote.finish(next(iter(remote.runs)), Outcome.completed("Devis prêt."))
        await tasks.wait(task.id)
    [ended] = await journal.history(TaskEnded)
    assert ended.files == (kept,) and blobs.blobs[kept.digest] == b"%PDF-1.7 devis"


async def test_a_revoked_key_stays_revoked_and_the_executor_works_without_nestor_s_tools() -> None:
    journal, remote = Journal(MemoryEventLog()), FakeRemote()
    executor = Reaching(remote, duration_s=0.0)
    executor.name = "codex"
    keys = await keys_for(journal, "codex")
    async with TaskManager(journal, [executor], keys=keys) as tasks:
        await keys.revoke("codex")
        await tasks.wait((await tasks.delegate("Corrige le test", origin=VOICE)).id)
        await keys.issue("codex")
        await tasks.wait((await tasks.delegate("Et celui-là", origin=VOICE)).id)
    first, second = (r.assignment for r in remote.runs.values())
    assert (first.task, first.access) == (None, None), "no key made behind the person's back"
    assert second.task and second.access, "a key made again works again"

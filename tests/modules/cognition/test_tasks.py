"""Durable tasks: threads of turns with an executor, started and directed from the conversation, followed in the
background, taken up again after a restart."""

import asyncio
from typing import Any

import pytest

from nestor.core import Capabilities, ContractError, PersonId
from nestor.modules.channels import Address, Attachment, AttachmentKind, Medium
from nestor.modules.cognition import Executor, Notify, Outcome, Progress, TaskState, TurnStatus
from nestor.modules.cognition.delegation import (
    CONTINUE,
    RESUME,
    Assignment,
    Directed,
    ExecutorKeys,
    NestorTools,
    TaskArchived,
    TaskCreated,
    TaskRenamed,
    TaskSteered,
    TurnAttached,
    TurnEnded,
    TurnRetried,
    TurnStarted,
    TurnStepped,
    TurnStopRequested,
)
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import INTERRUPTED, NOTES, TaskManager
from nestor.modules.cognition.delegation.types import STOPPED_FOR
from nestor.modules.cognition.tools import Risk, ToolContext, ToolFailed
from nestor.modules.conversation import Attached, Conversations, TurnContext
from nestor.modules.household import Person
from nestor.modules.identity import Speaker
from nestor.modules.journal import BlobRef, FileRef, Journal
from nestor.testing.cognition import (
    FakeRemote,
    RemoteExecutorContract,
    RemoteRun,
    ScriptedExecutor,
    ScriptedRemoteExecutor,
)
from nestor.testing.connectors import MemoryVault
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

VOICE = Address("voice", "salon")
MATHIS, LEA = PersonId("mathis"), PersonId("lea")


class TestScriptedRemoteExecutor(RemoteExecutorContract):
    def setup_method(self) -> None:
        self.remote = FakeRemote()

    def executor(self) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(self.remote, result="Il fera 18 degrés.")

    def slow_executor(self) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(duration_s=None)

    def failing_executor(self) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(refuses=True)

    def asking_executor(self) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(asks="Quelle marque ?")


def data(output: object) -> dict[str, Any]:
    assert isinstance(output, dict)
    return output


class Stubborn(ScriptedRemoteExecutor):
    name = "stubborn"


class Forgetful(ScriptedExecutor):
    """Keeps no session and takes nothing while it works: what the turns before were is told to it."""

    name = "forgetful"
    capabilities = Capabilities.of()


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


async def started(tasks: TaskManager, instruction: str = "Analyse le dépôt", **given: Any) -> Any:
    """A task started on `executor`, by default the manager's only one."""
    executor = given.pop("executor", next(iter(tasks.executors), "codex"))
    return await tasks.start_task(
        instruction, title=given.pop("title", instruction), origin=VOICE, executor=executor, **given
    )


async def test_a_task_runs_in_the_background_and_is_logged_turn_by_turn(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor("Trois soucis trouvés.")]) as tasks:
        task = await started(tasks, owner=MATHIS, notify=Notify.MESSAGE)
        assert task.state is TaskState.WORKING
        outcome = await tasks.wait(task.id)

    assert outcome.status is TurnStatus.COMPLETED and outcome.result == "Trois soucis trouvés."
    assert task.state is TaskState.READY
    logged = await journal.history(TaskCreated, TurnStarted, TurnAttached, TurnStepped, TurnEnded)
    assert [e.event_type for e in logged] == [
        "task.created",
        "task.turn.attached",
        "task.turn.step",
        "task.turn.ended",
    ], "its first turn opened with it, its steps before its end"
    created = logged[0]
    assert isinstance(created, TaskCreated)
    assert (created.origin, created.owner, created.notify, created.by) == (VOICE, MATHIS, Notify.MESSAGE, MATHIS)


async def test_a_task_goes_on_in_the_same_session_turn_after_turn(journal: Journal) -> None:
    executor = ScriptedExecutor("Fait.")
    async with TaskManager(journal, [executor]) as tasks:
        task = await started(tasks, "Écris pomme dans note.txt", owner=MATHIS)
        first = await tasks.wait(task.id)
        assert await tasks.direct(task.id, "Quel mot as-tu écrit ?", by=MATHIS) is Directed.STARTED
        await tasks.wait(task.id)
    assert first.session and [a.session for a in executor.assignments] == [None, first.session]
    assert executor.assignments[1].earlier == "", "it keeps its session: nothing to tell it again"
    assert len(task.turns) == 2 and executor.assignments[0].folder == executor.assignments[1].folder


async def test_an_executor_that_keeps_no_session_is_told_the_turns_before(journal: Journal) -> None:
    executor = Forgetful("Fait.")
    async with TaskManager(journal, [executor]) as tasks:
        task = await started(tasks, "Écris pomme dans note.txt")
        await tasks.wait(task.id)
        await tasks.direct(task.id, "Quel mot as-tu écrit ?", by=MATHIS)
        await tasks.wait(task.id)
    second = executor.assignments[1]
    assert second.session is None
    assert "Écris pomme dans note.txt" in second.earlier and "Fait." in second.earlier
    assert "Écris pomme" in second.brief(), "told in what it reads"


async def test_an_instruction_while_it_works_steers_the_turn(journal: Journal) -> None:
    executor = ScriptedExecutor(duration_s=30)
    async with TaskManager(journal, [executor]) as tasks:
        task = await started(tasks, "Mets à jour le site")
        await asyncio.sleep(0.01)
        assert await tasks.direct(task.id, "Ajoute aussi la page contact", by=MATHIS) is Directed.STEERED
        assert len(task.turns) == 1 and task.state is TaskState.WORKING, "the same turn goes on"
        assert [i for _, i in executor.steered] == ["Ajoute aussi la page contact"]
        assert [(s.instruction, s.by) for s in task.turn.steered] == [("Ajoute aussi la page contact", MATHIS)]
        executor.finish()
        await tasks.wait(task.id)
    [steered] = await journal.history(TaskSteered)
    assert (steered.taken, steered.by, steered.instruction) == (True, MATHIS, "Ajoute aussi la page contact")


async def test_an_executor_that_cannot_be_steered_is_stopped_and_told_the_new_direction(journal: Journal) -> None:
    executor = Forgetful(duration_s=30)
    async with TaskManager(journal, [executor]) as tasks:
        task = await started(tasks, "Mets à jour le site")
        await asyncio.sleep(0.01)
        assert await tasks.direct(task.id, "Plutôt la page contact", by=MATHIS) is Directed.STARTED
        await asyncio.sleep(0.01)
        assert [t.status for t in task.turns] == [TurnStatus.STOPPED, TurnStatus.RUNNING]
        assert task.turn.instruction == "Plutôt la page contact", "journaled as the person gave it"
        assert executor.assignments[-1].brief().startswith(STOPPED_FOR.format(instruction="Plutôt la page contact"))
        await tasks.stop(task.id)
    [steered] = await journal.history(TaskSteered)
    assert steered.taken is False and len(await journal.history(TurnStopRequested)) == 2


async def test_files_cannot_join_a_working_turn_they_open_the_next(journal: Journal) -> None:
    blobs = MemoryBlobStore()
    devis = await blobs.put(b"%PDF devis", "application/pdf")
    executor = ScriptedExecutor(duration_s=30)
    async with TaskManager(journal, [executor], blobs=blobs) as tasks:
        task = await started(tasks)
        await asyncio.sleep(0.01)
        directed = await tasks.direct(task.id, "Voici le devis", by=MATHIS, given=(FileRef(devis, "devis.pdf"),))
        assert directed is Directed.STARTED and executor.steered == []
        await asyncio.sleep(0.01)
        assert [f.name for f in executor.assignments[-1].files] == ["devis.pdf"]
        await tasks.stop(task.id)


async def test_a_turn_that_needs_its_owner_waits_and_their_answer_goes_on_in_the_thread(journal: Journal) -> None:
    executor = ScriptedExecutor(asks="Quelle marque est le lave-vaisselle ?")
    async with TaskManager(journal, [executor]) as tasks:
        task = await started(tasks, "Connecte le lave-vaisselle", owner=MATHIS)
        asking = await tasks.wait(task.id)
        assert (task.state, task.question) == (TaskState.WAITING, "Quelle marque est le lave-vaisselle ?")
        await tasks.direct(task.id, "C'est un Hisense", by=MATHIS)
        await tasks.wait(task.id)
    assert (task.state, task.question) == (TaskState.READY, None)
    assert executor.assignments[1].session == asking.session, "the answer goes on in the session that asked"
    [asked, answered] = await journal.history(TurnEnded)
    assert (asked.status, asked.question) == (TurnStatus.ASKED, "Quelle marque est le lave-vaisselle ?")
    assert answered.status is TurnStatus.COMPLETED


async def test_archiving_closes_a_question_and_an_instruction_opens_the_task_again(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor(asks="Laquelle ?")]) as tasks:
        task = await started(tasks, owner=MATHIS)
        await tasks.wait(task.id)
        await tasks.archive(task.id, by=MATHIS)
        assert (task.state, task.question) == (TaskState.ARCHIVED, None)
        assert tasks.of(MATHIS) == [], "put away"
        await tasks.direct(task.id, "La première", by=MATHIS)
        await tasks.wait(task.id)
        assert task.state is TaskState.READY and tasks.of(MATHIS) == [task]


async def test_a_task_comes_back_after_a_restart_as_it_was(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor("Fait.")]) as tasks:
        task = await started(tasks, owner=MATHIS, title="Site")
        first = await tasks.wait(task.id)
        await tasks.rename(task.id, "Site de la famille", by=MATHIS)
        await tasks.note(task, "Le site est dans /srv/site.")
        await tasks.archive(task.id)
    async with TaskManager(journal, [ScriptedExecutor()]) as restarted:
        again = restarted.tasks[task.id]
        assert again.turns[0].steered == task.turns[0].steered
        assert (again.title, again.state, again.session, again.notes) == (
            "Site de la famille",
            TaskState.ARCHIVED,
            first.session,
            ["Le site est dans /srv/site."],
        )
        assert [t.instruction for t in again.turns] == ["Analyse le dépôt"]
    assert [e.title for e in await journal.history(TaskRenamed)] == ["Site de la famille"]
    assert len(await journal.history(TaskArchived)) == 1


async def test_a_task_left_ready_is_archived_after_its_executor_s_delay_and_never_when_it_has_none(
    journal: Journal,
) -> None:
    kept, put_away = ScriptedExecutor(), Forgetful()
    kept.archive_after_days, put_away.archive_after_days = None, 0
    async with TaskManager(journal, [kept, put_away], sweep_s=0.01) as tasks:
        forever = await started(tasks, executor=kept.name)
        soon = await started(tasks, executor=put_away.name)
        await tasks.wait(forever.id)
        await tasks.wait(soon.id)
        for _ in range(200):
            if soon.state is TaskState.ARCHIVED:
                break
            await asyncio.sleep(0.01)
    assert (forever.state, soon.state) == (TaskState.READY, TaskState.ARCHIVED)
    [archived] = await journal.history(TaskArchived)
    assert (archived.task_id, archived.by) == (soon.id, None)


async def test_the_files_a_turn_made_are_kept_and_one_that_cannot_be_is_said_not_lost(journal: Journal) -> None:
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
        task = await started(tasks, "Écris-les")
        await tasks.wait(task.id)
    [ended] = await journal.history(TurnEnded)
    assert [blobs.blobs[f.blob.digest] for f in ended.files] == [b"kept"]
    assert ended.result == "Écrits.\nFiles not kept: b.txt (OSError)"
    async with TaskManager(Journal(MemoryEventLog()), [Writer()]) as nowhere:
        lost = await nowhere.wait((await started(nowhere, "Écris-les")).id)
    assert lost.result == "Écrits.\nFiles not kept: a.txt (nowhere to keep it); b.txt (nowhere to keep it)"


async def test_remote_work_survives_a_restart_and_is_not_started_twice(journal: Journal) -> None:
    remote = FakeRemote()
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)]) as tasks:
        task = await started(tasks, "Long travail")
        await asyncio.sleep(0.01)
    (ref,) = remote.runs
    assert remote.runs[ref].outcome is None, "a restart must not stop remote work"

    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)]) as restarted:
        remote.finish(ref, Outcome.completed("fini pendant le redémarrage", session="s1"))
        outcome = await restarted.wait(task.id)
        assert restarted.tasks[task.id].session == "s1"

    assert outcome.result == "fini pendant le redémarrage"
    assert len(remote.runs) == 1 and remote.runs[ref].follows == 2
    assert [e.ref for e in await journal.history(TurnAttached)] == [ref]


async def test_local_work_cut_by_a_restart_is_reported_not_lost(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor(duration_s=30)]) as tasks:
        task = await started(tasks, "Travail local")
        await asyncio.sleep(0.01)
    # the shutdown stopped it cleanly; now play a crash: a turn the journal still sees working
    await journal.publish(
        TaskCreated(
            source="test",
            task_id="crashed",
            title="X",
            executor="scripted-executor",
            origin=VOICE,
            turn_id="t1",
            instruction="x",
        )
    )
    async with TaskManager(journal, [ScriptedExecutor()]) as restarted:
        assert restarted.tasks[task.id].turn.status is TurnStatus.STOPPED
        assert restarted.tasks["crashed"].turn.outcome == Outcome.failed(INTERRUPTED)
    assert [e.task_id for e in await journal.history(TurnEnded)] == [task.id, "crashed"]


async def test_a_stop_is_confirmed_or_reported_unconfirmed(journal: Journal) -> None:
    stubborn = Stubborn(duration_s=None, confirms_stop=False)
    async with TaskManager(journal, [ScriptedRemoteExecutor(duration_s=None), stubborn]) as tasks:
        polite = await started(tasks, "a")
        hard = await started(tasks, "b", executor="stubborn")
        await asyncio.sleep(0.01)
        assert (await tasks.stop(polite.id)).status is TurnStatus.STOPPED
        assert (await tasks.stop(hard.id)).error == "stop not confirmed"
        assert (await tasks.stop(polite.id)).status is TurnStatus.STOPPED  # already over
        with pytest.raises(ContractError, match="no task 'nope'"):
            await tasks.stop("nope")
    assert len(await journal.history(TurnStopRequested)) == 2
    assert polite.state is TaskState.READY, "the task stays: only its turn stopped"


async def test_a_first_turn_stopped_keeps_its_session_for_the_next(journal: Journal) -> None:
    remote = FakeRemote()
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)]) as tasks:
        task = await started(tasks, "Mets à jour le site")
        await asyncio.sleep(0.01)
        [first] = remote.runs.values()
        await tasks.stop(task.id)
        assert task.session == first.session, "the session the stopped turn worked in"
        await tasks.direct(task.id, "Reprends", by=MATHIS)
        await asyncio.sleep(0.01)
        assert [r.assignment.session for r in remote.runs.values()][-1] == first.session
        await tasks.stop(task.id)


async def test_an_executor_that_hangs_on_a_stop_is_reported(journal: Journal) -> None:
    class Slow(Executor):
        """Takes far longer to stop than the manager is willing to wait."""

        name = "slow-to-stop"

        async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await asyncio.sleep(0.2)
            return Outcome.stopped()

    async with TaskManager(journal, [Slow()], stop_timeout_s=0.01) as tasks:
        task = await started(tasks, "x")
        await asyncio.sleep(0.01)
        assert (await tasks.stop(task.id)).error == "stop requested, not confirmed by the executor"
        assert (await tasks.wait(task.id)).status is TurnStatus.STOPPED


async def test_failures_end_the_turn_without_breaking_the_assistant(journal: Journal) -> None:
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
        ids = [(await started(tasks, "x", executor=e.name)).id for e in executors]
        errors = [(await tasks.wait(i)).error for i in ids]
    assert errors == [
        "RuntimeError: remote agent crashed",
        "scripted-remote: instruction refused",
        "ConnectionError: stream dropped",
    ]


async def test_delegating_needs_a_started_manager_and_a_known_executor(journal: Journal) -> None:
    with pytest.raises(ContractError, match="must be started"):
        await started(TaskManager(journal, [ScriptedExecutor()]), "x")
    async with TaskManager(journal, []) as none:
        with pytest.raises(ContractError, match="none is plugged in"):
            await started(none, "x")
    async with TaskManager(journal, [ScriptedExecutor()]) as tasks:
        with pytest.raises(ContractError, match="no executor named 'codex'"):
            await started(tasks, "x", executor="codex")


def tools_of(tasks: TaskManager) -> dict[str, Any]:
    return {t.name: t for t in Delegation(tasks).tools()}


async def test_the_agent_starts_directs_and_stops_its_tasks_through_its_tools(journal: Journal) -> None:
    mine = ToolContext(address=VOICE, speaker=Speaker.account(MATHIS))
    async with TaskManager(journal, [ScriptedRemoteExecutor(duration_s=None)]) as tasks:
        tools = tools_of(tasks)
        opened = data(
            await tools["start_task"].run(
                {
                    "executor": "scripted-remote",
                    "title": " Resto de samedi ",
                    "instruction": "Cherche un resto",
                    "notify": "message",
                },
                mine,
            )
        )
        task_id = str(opened["task_id"])
        await asyncio.sleep(0.01)  # the turn reaches its executor and hands its handle back
        listed = data(await tools["list_tasks"].run({}, mine))
        steered = data(await tools["continue_task"].run({"task": task_id, "instruction": "Pas trop cher"}, mine))
        stopped = data(await tools["stop_task"].run({"task": task_id}, mine))
        renamed = data(await tools["rename_task"].run({"task": task_id, "title": "Resto"}, mine))
        read = data(await tools["read_task"].run({"task": task_id}, mine))
        archived = data(await tools["archive_task"].run({"task": task_id}, mine))

    task = tasks.tasks[task_id]
    assert task.turns[0].notify is Notify.MESSAGE and task.owner == MATHIS
    assert [(t["task_id"], t["title"], t["state"]) for t in listed["tasks"]] == [
        (task_id, "Resto de samedi", "working")
    ]
    assert steered["directed"] == "steered" and stopped == {"stopped": True, "state": "ready"}
    assert renamed["title"] == "Resto" and read["turns"][0]["asked"] == "Cherche un resto"
    assert archived["state"] == "archived"


async def test_nobody_reaches_another_person_s_task(journal: Journal) -> None:
    mine = ToolContext(address=VOICE, speaker=Speaker.account(MATHIS))
    hers = ToolContext(address=VOICE, speaker=Speaker.account(LEA))
    nobody = ToolContext(address=VOICE)
    async with TaskManager(journal, [ScriptedExecutor(duration_s=30)]) as tasks:
        tools = tools_of(tasks)
        task_id = str(
            data(
                await tools["start_task"].run(
                    {"executor": "scripted-executor", "title": "Site", "instruction": "x"}, mine
                )
            )["task_id"]
        )
        for name, arguments in [
            ("continue_task", {"task": task_id, "instruction": "y"}),
            ("stop_task", {"task": task_id}),
            ("read_task", {"task": task_id}),
            ("rename_task", {"task": task_id, "title": "Autre"}),
            ("archive_task", {"task": task_id}),
        ]:
            for context in (hers, nobody):
                with pytest.raises(ToolFailed, match="of theirs"):
                    await tools[name].run(arguments, context)
        assert data(await tools["list_tasks"].run({}, hers)) == {"tasks": []}
        assert tasks.tasks[task_id].state is TaskState.WORKING, "untouched"
        await tasks.stop(task_id)


async def test_the_model_names_the_executor_even_when_there_is_only_one(journal: Journal) -> None:
    context = ToolContext(address=VOICE, speaker=Speaker.account(MATHIS))
    async with TaskManager(journal, [ScriptedExecutor()]) as tasks:
        start = tools_of(tasks)["start_task"]
        assert "executor" in start.spec.parameters["required"]
        with pytest.raises(ToolFailed, match="no executor named ''"):
            await start.run({"title": "PR", "instruction": "Ouvre une PR"}, context)
    assert tasks.tasks == {}, "never handed to the only one by default"


async def test_an_executor_with_real_power_is_sensitive_for_the_toolbox_to_confirm(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor(sensitive=True), Forgetful()]) as tasks:
        tools = tools_of(tasks)
        start, cont = tools["start_task"], tools["continue_task"]
        assert start.account_vouches and cont.account_vouches, "their own account in conversation is enough"
        assert "executor" in start.spec.parameters["required"], "with two, the model names the one it means"
        assert start.risk_of({"executor": "scripted-executor"}) is Risk.SENSITIVE
        assert start.risk_of({"executor": "forgetful"}) is Risk.WRITE
        task = await started(tasks, executor="forgetful")
        assert cont.risk_of({"task": task.id}) is Risk.WRITE
        await tasks.wait(task.id)


async def test_the_files_of_the_message_answered_go_with_an_instruction_or_those_named() -> None:
    journal, blobs, remote = Journal(MemoryEventLog()), MemoryBlobStore(), FakeRemote()
    chat, mathis = Address("telegram", "42"), Speaker.account(MATHIS)
    devis, other, photo, voice = [
        await blobs.put(content, media)
        for content, media in [
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
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)], blobs=blobs) as tasks:
        tool = tools_of(tasks)["start_task"]
        answered = data(
            await tool.run({"executor": "scripted-remote", "title": "Devis", "instruction": "Compare"}, context)
        )
        named = data(
            await tool.run(
                {
                    "executor": "scripted-remote",
                    "title": "Tous",
                    "instruction": "Compare",
                    "files": ["devis.pdf", "image.jpg", "devis (2).pdf"],
                },
                context,
            )
        )
        await asyncio.sleep(0.01)
        with pytest.raises(ToolFailed, match=r"no file named nope\.pdf"):
            await tool.run(
                {"executor": "scripted-remote", "title": "X", "instruction": "x", "files": ["nope.pdf"]}, context
            )
        for task_id in (answered["task_id"], named["task_id"]):
            await tasks.stop(str(task_id))
    assert [g.name for g in tasks.tasks[str(answered["task_id"])].given] == ["devis (2).pdf"], "this message's file"
    assert [g.name for g in tasks.tasks[str(named["task_id"])].given] == ["devis.pdf", "image.jpg", "devis (2).pdf"]


async def test_the_delegation_tools_refuse_bad_arguments(journal: Journal) -> None:
    context = ToolContext(address=VOICE, speaker=Speaker.account(MATHIS))
    async with TaskManager(journal, [ScriptedExecutor(), ScriptedRemoteExecutor()]) as tasks:
        tools = tools_of(tasks)
        assert "executor" in data(tools["start_task"].spec.parameters["properties"])
        with pytest.raises(ToolFailed, match="notify must be one of"):
            await tools["start_task"].run({"title": "X", "instruction": "x", "notify": "pigeon"}, context)
        with pytest.raises(ToolFailed, match="no executor named"):
            await tools["start_task"].run({"title": "X", "instruction": "x", "executor": "codex"}, context)
        for unnamed in ({"instruction": "x"}, {"title": " ", "instruction": "x"}):
            with pytest.raises(ToolFailed, match="title must be a short name"):
                await tools["start_task"].run(unnamed, context)
        assert tasks.tasks == {}, "nothing started"


async def test_the_instructions_say_what_executors_can_do_and_what_their_tasks_wait_on(journal: Journal) -> None:
    def turn(person: Any = None) -> TurnContext:
        return TurnContext(person=person, speaker=Speaker.unknown(), address=VOICE, said=None)

    async with TaskManager(journal, []) as none:
        assert Delegation(none).tools() == ()
        assert "No executor is plugged in" in Delegation(none).guidance()
        assert await Delegation(none).context(turn()) == {}
    async with TaskManager(journal, [ScriptedExecutor(asks="Quel jour ?")]) as tasks:
        task = await started(tasks, "Réserver un resto", owner=MATHIS)
        await tasks.wait(task.id)
        delegation = Delegation(tasks)
        guidance = delegation.guidance()
        theirs = str(await delegation.context(turn(Person(id=MATHIS, name="Mathis"))))
        hers = await delegation.context(turn(Person(id=LEA, name="Léa")))
        mentioned = list(delegation.mentionable(Person(id=MATHIS, name="Mathis")))
    assert "scripted-executor: carry out scripted test tasks" in guidance and "Réserver" not in guidance
    assert "Réserver un resto" in theirs and "Quel jour ?" in theirs
    assert hers == {}, "another person's tasks are not hers"
    assert [(m.kind.value, m.id) for m in mentioned][-1] == ("task", task.id)


class Reaching(ScriptedRemoteExecutor):
    """A remote executor that reaches Nestor's MCP server with what Nestor passes it."""

    nestor_tools = NestorTools.PASSED


async def keys_for(journal: Journal, *executors: str) -> ExecutorKeys:
    keys = ExecutorKeys(journal, MemoryVault(), "https://nestor.example/mcp", executors)
    await keys.start()
    return keys


async def test_each_turn_gets_a_capability_good_for_it_while_it_works() -> None:
    journal, remote = Journal(MemoryEventLog()), FakeRemote()
    reaching, plain = Reaching(remote, duration_s=None), ScriptedRemoteExecutor(FakeRemote(), duration_s=None)
    reaching.name, plain.name = "codex", "hermes"
    keys = await keys_for(journal, "codex", "hermes")
    async with TaskManager(journal, [reaching, plain], keys=keys) as tasks:
        task = await started(tasks, "Corrige le test", executor="codex")
        other = await started(tasks, "Cherche un vol", executor="hermes")
        await asyncio.sleep(0.01)
        [given] = [r.assignment for r in remote.runs.values()]
        assert given.task and given.task.startswith("nstt_") and given.access is not None
        assert given.access.url == "https://nestor.example/mcp" and keys.caller(given.access.key) == "codex"
        assert given.task in given.brief() and "task_brief" in given.brief()
        assert [r.assignment.task for r in plain.remote.runs.values()] == [None], "it cannot reach"
        assert await tasks.admit("codex", given.task, "task_brief") is task
        assert await tasks.admit("hermes", given.task, "task_brief") is None, "another executor's task"
        assert await tasks.admit("codex", "nstt_guessed", "task_brief") is None
        [opened] = [e for e in await journal.history(TaskCreated) if e.task_id == task.id]
        assert opened.capability and given.task not in str(opened.to_record()), "only its digest is journaled"
        remote.finish(next(iter(remote.runs)), Outcome.completed("ok"))
        await tasks.wait(task.id)
        assert await tasks.admit("codex", given.task, "task_brief") is None, "its turn ended"
        await tasks.direct(task.id, "Et l'autre test", by=MATHIS)
        await asyncio.sleep(0.01)
        second = [r.assignment for r in remote.runs.values()][-1]
        assert second.task and second.task != given.task and await tasks.admit("codex", second.task, "note") is task
        await tasks.stop(task.id)
        await tasks.stop(other.id)


async def test_a_capability_still_works_for_a_remote_turn_followed_again_after_a_restart() -> None:
    journal, remote = Journal(MemoryEventLog()), FakeRemote()
    executor = Reaching(remote, duration_s=None)
    executor.name = "codex"
    async with TaskManager(journal, [executor], keys=await keys_for(journal, "codex")) as tasks:
        task = await started(tasks, "Corrige le test")
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


async def test_a_file_an_executor_hands_back_while_it_works_goes_with_the_turn() -> None:
    journal, blobs, remote = Journal(MemoryEventLog()), MemoryBlobStore(), FakeRemote()
    executor = Reaching(remote, duration_s=None)
    async with TaskManager(journal, [executor], blobs=blobs) as tasks:
        task = await started(tasks, "Écris le devis")
        await asyncio.sleep(0.01)
        pdf = Attachment(
            kind=AttachmentKind.FILE, data=b"%PDF-1.7 devis", media_type="application/pdf", name="devis.pdf"
        )
        kept = await tasks.add_file(task, task.turn.id, pdf)
        remote.finish(next(iter(remote.runs)), Outcome.completed("Devis prêt."))
        await tasks.wait(task.id)
    [ended] = await journal.history(TurnEnded)
    assert ended.files == (kept,) and blobs.blobs[kept.blob.digest] == b"%PDF-1.7 devis"


async def test_notes_stay_with_the_task_and_the_oldest_give_way(journal: Journal) -> None:
    async with TaskManager(journal, [ScriptedExecutor()]) as tasks:
        task = await started(tasks)
        for n in range(NOTES + 2):
            await tasks.note(task, f"note {n}")
        with pytest.raises(ContractError, match="empty note"):
            await tasks.note(task, "   ")
    assert len(task.notes) == NOTES and task.notes[0] == "note 2"


async def test_a_revoked_key_stays_revoked_and_the_executor_works_without_nestor_s_tools() -> None:
    journal, remote = Journal(MemoryEventLog()), FakeRemote()
    executor = Reaching(remote, duration_s=0.0)
    executor.name = "codex"
    keys = await keys_for(journal, "codex")
    async with TaskManager(journal, [executor], keys=keys) as tasks:
        await keys.revoke("codex")
        await tasks.wait((await started(tasks, "Corrige le test")).id)
        await keys.issue("codex")
        await tasks.wait((await started(tasks, "Et celui-là")).id)
    first, second = (r.assignment for r in remote.runs.values())
    assert (first.task, first.access) == (None, None), "no key made behind the person's back"
    assert second.task and second.access, "a key made again works again"


class Unstoppable(ScriptedRemoteExecutor):
    """Cannot take an instruction while it works, and never confirms a stop."""

    name = "unstoppable"
    capabilities = Capabilities.of(RESUME, CONTINUE)


async def test_an_instruction_is_not_given_while_the_turn_that_works_could_not_be_stopped(journal: Journal) -> None:
    remote = FakeRemote()
    async with TaskManager(journal, [Unstoppable(remote, duration_s=None, confirms_stop=False)]) as tasks:
        task = await started(tasks, "Mets à jour le site", owner=MATHIS)
        await asyncio.sleep(0.01)
        mine = ToolContext(address=VOICE, speaker=Speaker.account(MATHIS))
        said = data(await tools_of(tasks)["continue_task"].run({"task": task.id, "instruction": "Plutôt ça"}, mine))
        assert said["directed"] == "busy" and "could not be stopped" in str(said["note"]), "the model tells the person"
        assert len(task.turns) == 1 and len(remote.runs) == 1, "never two turns of a task at once"
        assert await journal.history(TurnStarted, TaskSteered) == [], "the instruction was not given"
        remote.finish(next(iter(remote.runs)), Outcome.completed("fini"))
        await tasks.wait(task.id)


class TakesAsItEnds(ScriptedRemoteExecutor):
    """Takes the instruction, and its turn ends right then, before Nestor hears it was taken."""

    async def steer(self, handle: str, instruction: str) -> bool:
        taken = await super().steer(handle, instruction)
        self.remote.finish(handle, Outcome.completed("fini, consigne comprise"))
        await asyncio.sleep(0.01)
        return taken


async def test_an_instruction_the_executor_took_is_not_given_again_when_its_turn_ended_meanwhile(
    journal: Journal,
) -> None:
    remote = FakeRemote()
    async with TaskManager(journal, [TakesAsItEnds(remote, duration_s=None)]) as tasks:
        task = await started(tasks, "Mets à jour le site")
        await asyncio.sleep(0.01)
        assert await tasks.direct(task.id, "Ajoute la page contact", by=MATHIS) is Directed.STEERED
        await tasks.wait(task.id)
    assert len(task.turns) == 1 and len(remote.runs) == 1, "taken once, not run again in a turn of its own"
    [steered] = await journal.history(TaskSteered)
    assert steered.taken and [s.instruction for s in task.turn.steered] == ["Ajoute la page contact"]


async def test_an_event_of_one_turn_never_changes_another(journal: Journal) -> None:
    remote = FakeRemote()
    remote.runs["r2"] = RemoteRun(Assignment("Et la page contact"), "s2")
    remote.sessions.add("s2")
    for event in (
        TaskCreated(source="t", task_id="k", title="Site", executor="scripted-remote", origin=VOICE, turn_id="t1",
                    instruction="Mets à jour le site"),
        TurnEnded(source="t", task_id="k", turn_id="t1", status=TurnStatus.COMPLETED, result="fait", duration_s=1,
                  executor_session="s1"),
        TurnStarted(source="t", task_id="k", turn_id="t2", instruction="Et la page contact"),
        TurnAttached(source="t", task_id="k", turn_id="t2", ref="r2", executor_session="s2"),
        TaskSteered(source="t", task_id="k", turn_id="t1", instruction="trop tard", taken=True),
        TurnEnded(source="t", task_id="k", turn_id="t1", status=TurnStatus.FAILED, error="en retard", duration_s=1,
                  executor_session="s1"),
        TurnEnded(source="t", task_id="k", turn_id="nope", status=TurnStatus.FAILED, error="?", duration_s=1),
    ):  # fmt: skip
        await journal.publish(event)
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote, duration_s=None)]) as tasks:
        task = tasks.tasks["k"]
        assert task.state is TaskState.WORKING and task.turn.status is TurnStatus.RUNNING, (
            "the late end was the first's"
        )
        assert task.session == "s2" and task.turn.steered == []
        assert [s.instruction for s in task.turns[0].steered] == ["trop tard"]
        remote.finish("r2", Outcome.completed("ok"))
        await tasks.wait("k")


async def test_files_are_named_apart_across_the_whole_task(journal: Journal) -> None:
    blobs = MemoryBlobStore()
    first, other = await blobs.put(b"%PDF un", "application/pdf"), await blobs.put(b"%PDF deux", "application/pdf")
    executor = ScriptedExecutor()
    async with TaskManager(journal, [executor], blobs=blobs) as tasks:
        task = await started(tasks, given=(FileRef(first, "devis.pdf"),))
        await tasks.wait(task.id)
        again = (FileRef(other, "devis.pdf"), FileRef(first, "devis.pdf"))  # another file, then the same one again
        await tasks.direct(task.id, "Et celui-là", by=MATHIS, given=again)
        await tasks.wait(task.id)
    assert [f.name for f in executor.assignments[1].files] == ["devis (2).pdf", "devis.pdf"], "one folder per task"
    assert [f.name for f in task.turns[1].given] == ["devis (2).pdf", "devis.pdf"]


async def test_a_session_the_executor_lost_is_left_and_the_turn_runs_again_once_in_a_new_one(journal: Journal) -> None:
    executor = ScriptedExecutor("Fait.")
    async with TaskManager(journal, [executor]) as tasks:
        task = await started(tasks, "Écris pomme dans note.txt")
        lost = (await tasks.wait(task.id)).session
        assert lost
        executor.forget(lost)
        await tasks.direct(task.id, "Quel mot as-tu écrit ?", by=MATHIS)
        outcome = await tasks.wait(task.id)
    assert outcome.status is TurnStatus.COMPLETED and task.session and task.session != lost
    given, retried = executor.assignments[1:]
    assert (given.session, retried.session) == (lost, None)
    assert "Écris pomme dans note.txt" in retried.earlier, "told the turns before, its session gone"
    [again] = await journal.history(TurnRetried)
    assert again.turn_id == task.turn.id and len(await journal.history(TurnEnded)) == 2


async def test_a_turn_runs_again_only_once_and_its_lost_session_is_never_given_again(journal: Journal) -> None:
    """Its new session lost as well, followed again after a restart: the turn fails, the task keeps no session."""
    remote = FakeRemote()
    remote.runs["r1"] = RemoteRun(Assignment("Mets à jour le site"), "s2")
    remote.finish("r1", Outcome.lost("no rollout found for thread id s2"))
    for event in (
        TaskCreated(source="t", task_id="k", title="Site", executor="scripted-remote", origin=VOICE, turn_id="t1",
                    instruction="Mets à jour le site"),
        TurnRetried(source="t", task_id="k", turn_id="t1", error="no rollout found for thread id s1"),
        TurnAttached(source="t", task_id="k", turn_id="t1", ref="r1", executor_session="s2"),
    ):  # fmt: skip
        await journal.publish(event)
    async with TaskManager(journal, [ScriptedRemoteExecutor(remote)]) as tasks:
        outcome = await tasks.wait("k")
        task = tasks.tasks["k"]
    assert (outcome.status, task.session, len(remote.runs)) == (TurnStatus.FAILED, None, 1)
    assert len(await journal.history(TurnRetried)) == 1

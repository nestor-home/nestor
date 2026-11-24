"""Codex executor: the remote executor contract against a fake `codex app-server` reached through a relay, as on a
server, then what only this protocol can break (sessions that end, approvals, files handed back, threads that go on,
steering, stops)."""

import asyncio
import json
import os
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from nestor.adapters.executors.codex import CodexSettings, Sandbox, build
from nestor.adapters.executors.common import MAX_FILES
from nestor.core import ContractError, Health, ProviderError
from nestor.core.i18n import Locale, Message
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition.delegation import Assignment, Handle, NestorAccess, Progress, TurnStatus
from nestor.modules.journal import FileRef
from nestor.runtime import Services
from nestor.testing.cognition import RemoteExecutorContract
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryBlobStore

from .fakes import CWD, REPORT, TASK, FakeCodex


class TestCodexExecutor(RemoteExecutorContract):
    @pytest.fixture(autouse=True)
    async def served(self) -> AsyncIterator[None]:
        async with (
            FakeCodex() as self.codex,
            FakeCodex(holds=True) as self.held,
            FakeCodex(fails=True) as self.failing,
            FakeCodex(report=REPORT | {"question": "Quel fichier ?"}) as self.asking,
        ):
            yield

    def executor(self) -> Any:
        return self.codex.executor()

    def slow_executor(self) -> Any:
        return self.held.executor()

    def failing_executor(self) -> Any:
        return self.failing.executor()

    def asking_executor(self) -> Any:
        return self.asking.executor()


async def submitted(codex: FakeCodex, **options: Any) -> tuple[Any, str]:
    executor = codex.executor(**options)
    await executor.start()
    return executor, (await executor.submit(Assignment("Corrige le test."))).ref


async def test_the_task_runs_where_and_how_the_configuration_says() -> None:
    async with FakeCodex() as codex:
        options = {
            "model": "gpt-6.1",
            "sandbox": Sandbox.READ_ONLY,
            "config": {"mcp_servers": {}},
            "instructions": "Sois bref.",
        }
        async with codex.executor(**options) as executor:
            await executor.run(Assignment("Corrige le test."), Progress())
    [started] = [params for method, params in codex.requests if method == "thread/start"]
    [folder] = codex.folders
    assert folder == f"{CWD}/task", "the task's own folder, under the working directory"
    assert {k: started[k] for k in ("cwd", "sandbox", "approvalPolicy", "model", "config")} == {
        "cwd": folder,
        "sandbox": "read-only",
        "approvalPolicy": "never",
        "model": "gpt-6.1",
        "config": {"mcp_servers": {}},
    }
    instructions = started["developerInstructions"]
    assert instructions.startswith("Sois bref.") and "`files`" in instructions and "`question`" in instructions
    [turn] = [params for method, params in codex.requests if method == "turn/start"]
    assert turn["input"][0]["text"].startswith("Corrige le test.")
    assert turn["outputSchema"]["required"] == ["report", "files", "question"]


async def test_the_files_sent_with_a_task_wait_in_its_own_folder_and_the_brief_names_them() -> None:
    store = MemoryBlobStore()
    sent = (FileRef(await store.put(b"%PDF devis", "application/pdf"), "devis.pdf"),)
    async with FakeCodex() as codex, codex.executor() as executor:
        await executor.run(Assignment("Corrige le devis.", folder="task-a", files=sent, reader=store.get), Progress())
        await executor.run(Assignment("Corrige-le encore.", folder="task-b", files=sent, reader=store.get), Progress())
    first, second = codex.folders
    assert (first, second) == (f"{CWD}/task-a", f"{CWD}/task-b"), "each task its own folder"
    assert (codex.files[f"{first}/devis.pdf"], codex.files[f"{second}/devis.pdf"]) == (b"%PDF devis", b"%PDF devis")
    turn = next(params for method, params in codex.requests if method == "turn/start")
    assert f"Files sent with this instruction, in {first}: devis.pdf." in turn["input"][0]["text"]


async def test_nestor_s_mcp_server_joins_the_thread_s_own_servers_for_that_thread_only() -> None:
    access = NestorAccess(url="https://nestor.example/mcp", key="nstx_secret-key")
    configured = {"mcp_servers": {"docs": {"url": "https://docs.example/mcp"}}, "model_reasoning_effort": "low"}
    async with FakeCodex() as codex, codex.executor(config=configured) as executor:
        await executor.run(Assignment("Corrige le test.", task="nstt_task", access=access), Progress())
        await executor.run(Assignment("Et celui-là."), Progress())
    first, second = [params for method, params in codex.requests if method == "thread/start"]
    nestor = {"url": access.url, "http_headers": {"Authorization": "Bearer nstx_secret-key"}}
    assert first["config"] == {
        "mcp_servers": {"docs": {"url": "https://docs.example/mcp"}, "nestor": nestor},
        "model_reasoning_effort": "low",
    }
    assert second["config"] == configured, "the configured servers are left as they are"
    turn = next(params for method, params in codex.requests if method == "turn/start")
    assert 'task="nstt_task"' in turn["input"][0]["text"]


async def test_the_report_is_the_final_answer_and_what_the_agent_does_is_progress_without_command_lines() -> None:
    steps: list[str] = []
    async with FakeCodex() as codex, codex.executor() as executor:
        outcome = await executor.run(Assignment("Corrige le test."), Progress(steps.append))
    assert outcome.result == "C'est fait." and outcome.files == ()
    assert steps == [
        "running a command",
        "editing: src/a.py",
        "nestor: read_result",
        "web search: pytest asyncio",
        "drawing an image",
        "Je lance les tests.",
        "Lire le test, le corriger.",
    ]
    assert not any("ls" in step.split() or "bash" in step for step in steps), "a command line may carry a secret"


async def test_a_report_with_a_question_ends_the_turn_asked_in_its_thread() -> None:
    asking = REPORT | {"report": "J'ai trouvé deux devis.", "question": "Lequel corriger ?"}
    handles: list[Handle] = []
    async with FakeCodex(report=asking) as codex, codex.executor() as executor:
        outcome = await executor.run(Assignment("Corrige le devis."), Progress(on_attach=handles.append))
    [thread] = codex.threads
    assert (outcome.status, outcome.question, outcome.result) == (
        TurnStatus.ASKED,
        "Lequel corriger ?",
        "J'ai trouvé deux devis.",
    )
    assert [h.session for h in handles] == [thread], "the answer goes on in its thread"


async def test_a_later_turn_goes_on_in_the_task_s_thread_and_folder() -> None:
    handles: list[Handle] = []
    async with FakeCodex() as codex, codex.executor() as executor:
        await executor.run(Assignment("Corrige le test.", folder="task-a"), Progress(on_attach=handles.append))
        later = Assignment("Et l'autre.", session=handles[0].session, folder="task-a")
        await executor.run(later, Progress(on_attach=handles.append))
    [thread] = codex.threads.values()
    assert [h.session for h in handles] == [thread.id, thread.id]
    assert [t.objective.split("\n")[0] for t in thread.turns] == ["Corrige le test.", "Et l'autre."]
    methods = [m for m, _ in codex.requests]
    assert methods.count("thread/start") == 1 and "thread/resume" not in methods, "loaded in this session already"
    assert codex.folders == [f"{CWD}/task-a", f"{CWD}/task-a"], "the same folder, made again harmlessly"


async def test_a_later_turn_after_a_restart_resumes_the_thread_first() -> None:
    access = NestorAccess(url="https://nestor.example/mcp", key="nstx_secret-key")
    handles: list[Handle] = []
    async with FakeCodex() as codex:
        async with codex.executor() as before:
            await before.run(Assignment("Corrige le test."), Progress(on_attach=handles.append))
        first = handles[0].session
        async with codex.executor() as restarted:
            later = Assignment("Et l'autre.", session=first, access=access)
            then = await asyncio.wait_for(restarted.run(later, Progress()), 5)  # unheard if the thread is not resumed
    assert then.status is TurnStatus.COMPLETED
    after = [(m, p) for m, p in codex.requests if m in ("thread/start", "thread/resume", "turn/start")]
    assert [m for m, _ in after] == ["thread/start", "turn/start", "thread/resume", "turn/start"]
    resumed, started = after[2][1], after[3][1]
    assert resumed["threadId"] == started["threadId"] == first
    assert resumed["config"]["mcp_servers"]["nestor"]["url"] == access.url, "the thread reaches Nestor again"


async def test_an_instruction_is_steered_into_the_working_turn_only() -> None:
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex)
        assert await executor.steer(ref, "Fais-le plus court.") is True
        [(_, steering)] = [(m, p) for m, p in codex.requests if m == "turn/steer"]
        thread, turn, _ = ref.split(":")
        assert (steering["threadId"], steering["expectedTurnId"]) == (thread, turn)
        assert codex.turn(ref).steered == ["Fais-le plus court."]
        await codex.finish(ref)
        assert (await executor.follow(ref, Progress())).status is TurnStatus.COMPLETED
        assert await executor.steer(ref, "Encore plus court.") is False, "the turn ended"
        assert await executor.steer("not-a-reference", "Plus court.") is False
        await executor.close()
    assert codex.turn(ref).steered == ["Fais-le plus court."]


async def test_a_final_answer_that_is_not_a_structured_report_is_the_report() -> None:
    async with FakeCodex(report="Tout est vert.") as codex, codex.executor() as executor:
        outcome = await executor.run(Assignment("Lance les tests."), Progress())
    assert outcome.status is TurnStatus.COMPLETED and outcome.result == "Tout est vert."


async def test_the_files_the_report_lists_come_back_from_the_task_s_own_folder_only() -> None:
    pdf = b"%PDF-1.7 devis"
    files = {f"{TASK}/devis.pdf": pdf, f"{TASK}/big.bin": b"x" * 2_000, "/etc/passwd": b"root:x:0:0"}
    listed = [
        "devis.pdf",
        f"{TASK}/big.bin",
        "/etc/passwd",
        f"{TASK}/../../etc/passwd",
        f"{TASK}/missing.txt",
        TASK + "/sub",
    ]
    files[f"{TASK}/sub/inner.txt"] = b"inner"
    files["/srv/codex/.codex/auth.json"] = b'{"token": "secret"}'
    links = {f"{TASK}/auth.json": "/srv/codex/.codex/auth.json", f"{TASK}/home": "/srv/codex/.codex"}
    files[f"{TASK}/locked.txt"] = b"mine"
    files[f"{CWD}/other.txt"] = b"another task's"
    listed += ["auth.json", "home/auth.json", "locked.txt", f"{TASK}/../other.txt"]
    codex = FakeCodex(files=files, links=links, report={"report": "Devis écrit.", "files": listed})
    async with codex, codex.executor(max_file_bytes=1_000) as executor:
        outcome = await executor.run(Assignment("Écris le devis."), Progress())
    [devis] = outcome.files
    assert (devis.name, devis.kind, devis.media_type, devis.data) == (
        "devis.pdf",
        AttachmentKind.FILE,
        "application/pdf",
        pdf,
    )
    assert outcome.result is not None and outcome.result.startswith("Devis écrit.\nFiles left out: ")
    for left in (
        "big.bin (larger than 1000 bytes)",
        "/etc/passwd (outside the working directory)",
        "missing.txt (No such",
        "sub (not a file)",
        "auth.json (a link, not followed)",
        "home/auth.json (a link, not followed)",
        "locked.txt (wc: ",
        "other.txt (outside the working directory)",
    ):
        assert left in outcome.result, left
    read = [params["path"] for method, params in codex.requests if method == "fs/readFile"]
    assert read == [f"{codex.folders[0]}/devis.pdf"], "nothing too large or outside is downloaded, not even by link"


async def test_no_more_files_than_the_limit_come_back() -> None:
    files = {f"{TASK}/{n}.txt": b"x" for n in range(MAX_FILES + 2)}
    codex = FakeCodex(files=files, report={"report": "Faits.", "files": list(files)})
    async with codex, codex.executor() as executor:
        outcome = await executor.run(Assignment("Écris-les."), Progress())
    assert len(outcome.files) == MAX_FILES and f"(more than {MAX_FILES} files)" in (outcome.result or "")


async def test_a_turn_still_running_is_followed_to_its_end_after_a_restart() -> None:
    async with FakeCodex(holds=True) as codex:
        first, ref = await submitted(codex)
        await first.close()  # Nestor stops; the daemon goes on
        async with codex.executor() as restarted:
            follow = asyncio.create_task(restarted.follow(ref, Progress()))
            await asyncio.sleep(0.3)
            await codex.finish(ref, report={"report": "Réparé.", "files": []})
            outcome = await asyncio.wait_for(follow, 5)
    assert outcome.result == "Réparé." and [m for m, _ in codex.requests].count("turn/start") == 1


async def test_a_turn_a_local_server_took_down_with_it_is_reported_cut_short() -> None:
    async with FakeCodex(holds=True, daemon=False) as codex:
        first, ref = await submitted(codex)
        await first.close()
        async with codex.executor() as restarted:
            outcome = await restarted.follow(ref, Progress())
    assert outcome.status is TurnStatus.FAILED and "stopped before it ended" in (outcome.error or "")


async def test_a_turn_that_failed_or_was_stopped_elsewhere_says_so_after_a_restart() -> None:
    async with FakeCodex(fails=True) as codex:
        _, ref = await submitted(codex)
        await asyncio.sleep(0.2)
        async with codex.executor() as restarted:
            outcome = await restarted.follow(ref, Progress())
    assert (outcome.status, outcome.error) == (TurnStatus.FAILED, "the model refused")
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex)
        codex.turn(ref).status = "interrupted"  # someone stopped it from Codex's own interface
        async with codex.executor() as restarted:
            assert (await restarted.follow(ref, Progress())).status is TurnStatus.STOPPED
        await executor.close()


async def test_a_session_lost_while_the_turn_goes_on_is_opened_again() -> None:
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex, reconnect_s=(0.1,))
        follow = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.3)
        codex.drop_sessions()  # the relay broke; the daemon still runs the turn
        await asyncio.sleep(0.5)
        await codex.finish(ref, report={"report": "Réparé.", "files": []})
        outcome = await asyncio.wait_for(follow, 5)
        await executor.close()
    assert outcome.result == "Réparé."


async def test_a_codex_gone_for_good_while_following_is_a_failure() -> None:
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex, reconnect_s=(0.05, 0.05))
        follow = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.3)
        codex.go_away()
        outcome = await asyncio.wait_for(follow, 10)
        await executor.close()
    assert outcome.status is TurnStatus.FAILED and "lost contact with Codex" in (outcome.error or "")


async def test_the_end_of_a_turn_is_what_its_notification_says_while_the_history_lags() -> None:
    async with FakeCodex(lags=True) as codex, codex.executor() as executor:
        outcome = await asyncio.wait_for(executor.run(Assignment("Corrige le test."), Progress()), 5)
    assert outcome.result == "C'est fait."


async def test_a_session_that_never_answers_is_closed_with_its_process(tmp_path: Path) -> None:
    """Whether the answer times out or the submission is cancelled: no half-open session, no process left."""

    def silent(name: str) -> list[str]:
        pid = tmp_path / name
        return [
            sys.executable,
            "-c",
            f"import os, time; open({str(pid)!r}, 'w').write(str(os.getpid())); time.sleep(60)",
        ]

    async with FakeCodex() as codex, codex.executor(command=silent("timed-out"), timeout_s=0.5) as executor:
        with pytest.raises(ProviderError):
            await executor.submit(Assignment("Corrige le test."))
        assert executor.health() is Health.UNAVAILABLE
    async with FakeCodex() as codex, codex.executor(command=silent("cancelled"), timeout_s=30) as executor:
        submission = asyncio.create_task(executor.submit(Assignment("Corrige le test.")))
        await asyncio.sleep(0.5)
        submission.cancel()
        with pytest.raises(asyncio.CancelledError):
            await submission
    for name in ("timed-out", "cancelled"):
        with pytest.raises(ProcessLookupError):
            os.kill(int((tmp_path / name).read_text()), 0)


@pytest.mark.parametrize(
    ("asks", "answer"),
    [
        ("item/commandExecution/requestApproval", {"result": {"decision": "decline"}}),
        ("item/fileChange/requestApproval", {"result": {"decision": "decline"}}),
        ("execCommandApproval", {"result": {"decision": "denied"}}),
        ("item/tool/requestUserInput", {"result": {"answers": {}}}),
        ("mcpServer/elicitation/request", {"result": {"action": "decline"}}),
        ("item/permissions/requestApproval", {"error": {"code": -32601}}),
    ],
)
async def test_a_request_for_approval_or_input_is_declined(asks: str, answer: dict[str, Any]) -> None:
    async with FakeCodex(asks=asks) as codex, codex.executor() as executor:
        outcome = await executor.run(Assignment("Nettoie le disque."), Progress())
    assert outcome.status is TurnStatus.COMPLETED
    [given] = codex.answers
    key = next(iter(answer))
    assert {key: {k: given[key][k] for k in answer[key]}} == answer


async def test_a_confirmed_stop_returns_true() -> None:
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex)
        assert await executor.stop(ref) is True
        await executor.close()
    assert codex.turn(ref).status == "interrupted"


async def test_an_unconfirmed_stop_returns_false_after_the_timeout() -> None:
    async with FakeCodex(holds=True, confirms_stop=False) as codex:
        executor, ref = await submitted(codex, stop_timeout_s=0.3)
        assert await executor.stop(ref) is False
        await executor.close()


async def test_stopping_a_turn_that_already_finished_returns_false() -> None:
    async with FakeCodex() as codex:
        executor, ref = await submitted(codex)
        await executor.follow(ref, Progress())
        assert await executor.stop(ref) is False
        await executor.close()


async def test_stopping_or_following_an_unknown_task_fails_without_raising() -> None:
    async with FakeCodex() as codex, codex.executor() as executor:
        assert await executor.stop("thread-9:turn-9:task-x") is False
        unknown = await executor.follow("thread-9:turn-9:task-x", Progress())
        garbled = await executor.follow("no-separator", Progress())
    assert unknown.status is TurnStatus.FAILED and "invalid thread id" in (unknown.error or "")
    assert garbled.status is TurnStatus.FAILED


async def test_a_codex_that_cannot_be_reached_is_unavailable() -> None:
    async with (
        FakeCodex() as codex,
        codex.executor(command=["codex-that-is-not-installed", "app-server"], reconnect_s=()) as missing,
    ):
        with pytest.raises(ProviderError) as refused:
            await missing.submit(Assignment("Corrige le test."))
        outcome = await missing.run(Assignment("Corrige le test."), Progress())
        followed = await missing.follow("thread-1:turn-2:task-x", Progress())
        health = (missing.health(), missing.health_detail())
    assert refused.value.transient and outcome.status is TurnStatus.FAILED and followed.status is TurnStatus.FAILED
    assert health == (Health.UNAVAILABLE, Message.of("health-executor-unreachable", executor="codex"))


async def test_a_reply_outside_the_protocol_or_a_session_that_hangs_up_is_a_provider_error() -> None:
    async with FakeCodex(garbled=True) as codex, codex.executor() as executor:
        with pytest.raises(ProviderError) as garbled:
            await executor.submit(Assignment("Corrige le test."))
        followed = await executor.follow("thread-1:turn-2:task-x", Progress())
    async with FakeCodex(hangs_up=True) as codex, codex.executor() as executor:
        with pytest.raises(ProviderError) as hung_up:
            await executor.submit(Assignment("Corrige le test."))
    assert not garbled.value.transient and hung_up.value.transient
    assert followed.status is TurnStatus.FAILED and "unexpected reply" in (followed.error or "")


async def test_a_refused_thread_is_a_provider_error_from_a_codex_that_answers() -> None:
    async with FakeCodex(refuses=True) as codex, codex.executor() as executor:
        with pytest.raises(ProviderError) as refused:
            await executor.submit(Assignment("Corrige le test."))
        assert not refused.value.transient and executor.health() is Health.STARTED


async def test_using_the_executor_before_start_fails_clearly() -> None:
    async with FakeCodex() as codex:
        with pytest.raises(ContractError):
            await codex.executor().submit(Assignment("Corrige le test."))


async def test_the_plugin_builds_an_executor_described_by_its_configuration(tmp_path: Path) -> None:
    settings = CodexSettings(
        working_directory=CWD, description="corriger le code", sandbox=Sandbox.READ_ONLY, model="gpt-6.1"
    )
    services = Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    executor = build(settings, "codex-vps", services)
    assert (executor.name, executor.description, executor.brand) == ("codex-vps", "corriger le code", "codex")
    assert executor.details() == {"sandbox": "read-only", "model": "gpt-6.1"}
    assert executor.health() is Health.STARTED


@pytest.mark.live
@pytest.mark.skipif(shutil.which("codex") is None, reason="needs the codex command, signed in")
async def test_live_codex_writes_a_file_and_hands_it_back(tmp_path: Path) -> None:
    """Runs a real turn (cost) in a temporary directory, sandboxed to it."""
    async with build(
        CodexSettings(working_directory=str(tmp_path.resolve()), description="write files"),
        "codex",
        Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("en")),
    ) as executor:
        first = await executor.run(
            Assignment("Write a file hello.txt containing the word bonjour, then report."), Progress()
        )
    assert first.status is TurnStatus.COMPLETED, first
    assert [(f.name, f.data.strip()) for f in first.files] == [("hello.txt", b"bonjour")], json.dumps(first.result)
